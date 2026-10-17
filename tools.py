"""Tool definitions: Safe SQL Gateway, FAISS entity retriever, and Google Maps/Places APIs."""

from __future__ import annotations

import ast
import os
from typing import Any, Optional, Type

from googlemaps import Client as GoogleMaps
from langchain.agents.agent_toolkits import create_retriever_tool
from langchain.tools import BaseTool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, ConfigDict, Field

from sql_gateway import safe_run


# --- Schema Models for Tools ---

class SQLQueryInput(BaseModel):
    query: str = Field(..., description="A PostgreSQL SELECT or WITH query to execute")


class GeocodingInput(BaseModel):
    address: str = Field(..., description="The street address or place name to convert into geographic coordinates")


class DirectionsInput(BaseModel):
    origin: str = Field(..., description="The starting point address or coordinates (lat,lng)")
    destination: str = Field(..., description="The destination point address or coordinates (lat,lng)")


class PlacesInput(BaseModel):
    query: str = Field(..., description="What to search for, such as 'elementary school' or a place name")
    location: Optional[str] = Field(
        default=None,
        description="Latitude and longitude of the search center as 'lat,lng'",
    )
    radius: int = Field(default=5000, description="Search radius in meters")
    type: str = Field(default="school", description="Google Places type, such as school")


# --- Custom Tool Implementations ---

class SafeSQLQueryTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "sql_db_query"
    description: str = (
        "Execute a PostgreSQL SELECT query against the condo database. "
        "Only SELECT and WITH...SELECT queries are permitted. DML and DDL statements are blocked."
    )
    args_schema: Type[BaseModel] = SQLQueryInput
    db: Any = None

    def _run(self, query: str) -> str:
        output, validation = safe_run(self.db, query)
        return output


class GeocodingTool(BaseTool):
    name: str = "google_maps_geocoding"
    description: str = "Useful for converting street addresses into geographic coordinates (lat, lng)."
    args_schema: Type[BaseModel] = GeocodingInput
    gmaps_client: Any = None

    def _run(self, address: str) -> str:
        try:
            client = self.gmaps_client or GoogleMaps(os.getenv("GPLACES_API_KEY"))
            geocode_result = client.geocode(address)
            if geocode_result:
                location = geocode_result[0]["geometry"]["location"]
                return f"The coordinates for {address} are lat: {location['lat']}, lng: {location['lng']}."
            return f"Unable to find coordinates for address: {address}"
        except Exception as exc:
            return f"Error fetching coordinates: {str(exc)}"


class DirectionsTool(BaseTool):
    name: str = "google_maps_directions"
    description: str = "Useful for calculating driving distance and commute duration between two locations."
    args_schema: Type[BaseModel] = DirectionsInput
    gmaps_client: Any = None

    def _run(self, origin: str, destination: str) -> str:
        try:
            client = self.gmaps_client or GoogleMaps(os.getenv("GPLACES_API_KEY"))
            directions_result = client.directions(origin, destination, mode="driving")
            if directions_result:
                leg = directions_result[0]["legs"][0]
                distance = leg["distance"]["text"]
                duration = leg["duration"]["text"]
                return f"The driving distance from {origin} to {destination} is {distance} (approximately {duration} by car)."
            return f"Unable to calculate directions between {origin} and {destination}."
        except Exception as exc:
            return f"Error calculating directions: {str(exc)}"


class PlacesTool(BaseTool):
    name: str = "google_places"
    description: str = (
        "Search Google Places. Input a query plus optional location ('lat,lng'), "
        "radius in meters (default 5000), and type (default school)."
    )
    args_schema: Type[BaseModel] = PlacesInput
    gmaps_client: Any = None

    def _run(
        self,
        query: str,
        location: Optional[str] = None,
        radius: int = 5000,
        type: str = "school",
    ) -> str:
        api_key = os.getenv("GPLACES_API_KEY")
        if self.gmaps_client is None and not api_key:
            return "Google Places is unavailable because GPLACES_API_KEY is not set."
        try:
            client = self.gmaps_client or GoogleMaps(api_key)
            kwargs: dict[str, Any] = {"query": query}
            if location and str(location).strip():
                lat_str, lng_str = [part.strip() for part in str(location).split(",", 1)]
                kwargs["location"] = (float(lat_str), float(lng_str))
                kwargs["radius"] = int(radius)
            if type:
                kwargs["type"] = type
            results = client.places(**kwargs)
            places = results.get("results", []) if isinstance(results, dict) else []
            if not places:
                return f"No places found for {query}."
            lines = []
            for place in places[:5]:
                name = place.get("name", "")
                address = place.get("formatted_address") or place.get("vicinity") or ""
                loc = place.get("geometry", {}).get("location", {})
                lines.append(
                    f"{name} | {address} | lat: {loc.get('lat')}, lng: {loc.get('lng')}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error searching places: {str(exc)}"


# --- Helpers & Setup Function ---

def query_as_list(db: Any, query: str) -> list[str]:
    """Helper to query distinct proper nouns from PostgreSQL."""
    try:
        res = db.run(query)
        if not res:
            return []
        res_list = [el for sub in ast.literal_eval(res) for el in sub if el]
        res_list = [str(s).strip() for s in res_list]
        return list(set(filter(None, res_list)))
    except Exception as exc:
        print(f"Note: proper noun query failed: {exc}")
        return []


def _sql_tools(db: Any, llm: Any) -> list[BaseTool]:
    """SQL tools stay available even when Maps or embeddings fail."""
    safe_sql_tool = SafeSQLQueryTool(db=db)
    tools: list[BaseTool] = [safe_sql_tool]
    try:
        raw_tools = SQLDatabaseToolkit(db=db, llm=llm).get_tools()
        for tool in raw_tools:
            if tool.name != "sql_db_query":
                tools.append(tool)
    except Exception as exc:
        print(f"Note: SQL schema tools unavailable: {exc}")
    return tools


def _proper_noun_tool(db: Any) -> Optional[BaseTool]:
    """Build the FAISS retriever. Failure here must not discard the other tools."""
    try:
        addresses = query_as_list(db, "SELECT address FROM core_condobuilding")
        alt_names = query_as_list(db, "SELECT alt_name FROM core_condobuilding")
        entity_texts = list(set(addresses + alt_names))
        if not entity_texts:
            return None
        vector_db = FAISS.from_texts(entity_texts, OpenAIEmbeddings())
        retriever = vector_db.as_retriever(search_kwargs={"k": 5})
        description = (
            "Use to look up exact building names and addresses in the database. "
            "Input is an approximate or colloquial spelling of the proper noun; "
            "output is the closest valid database entity."
        )
        return create_retriever_tool(
            retriever,
            name="search_proper_nouns",
            description=description,
        )
    except Exception as exc:
        print(f"Note: proper noun index unavailable: {exc}")
        return None


def setup_tools(db: Any, llm: Any) -> list[BaseTool]:
    """Initialize and assemble agent tools."""
    tools = _sql_tools(db, llm)

    retriever_tool = _proper_noun_tool(db)
    if retriever_tool:
        tools.append(retriever_tool)

    gmaps_client = None
    gmaps_api_key = os.getenv("GPLACES_API_KEY")
    if gmaps_api_key:
        try:
            gmaps_client = GoogleMaps(gmaps_api_key)
        except Exception as exc:
            print(f"Note: Google Maps client unavailable: {exc}")

    try:
        tools.append(PlacesTool(gmaps_client=gmaps_client))
    except Exception as exc:
        print(f"Note: Google Places tool unavailable: {exc}")
    try:
        tools.append(GeocodingTool(gmaps_client=gmaps_client))
        tools.append(DirectionsTool(gmaps_client=gmaps_client))
    except Exception as exc:
        print(f"Note: Google Maps tools unavailable: {exc}")

    return tools
