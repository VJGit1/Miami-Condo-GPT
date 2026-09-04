"""Tool definitions: Safe SQL Gateway, FAISS entity retriever, and Google Maps/Places APIs."""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Type

from googlemaps import Client as GoogleMaps
from langchain.agents.agent_toolkits import create_retriever_tool
from langchain.tools import BaseTool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.tools import GooglePlacesTool
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


# --- Helpers & Setup Function ---

def query_as_list(db: Any, query: str) -> list[str]:
    """Helper to query distinct proper nouns from PostgreSQL."""
    try:
        res = db.run(query)
        if not res:
            return []
        res_list = [el for sub in ast.literal_eval(res) for el in sub if el]
        res_list = [re.sub(r"\b\d+\b", "", str(s)).strip() for s in res_list]
        return list(set(filter(None, res_list)))
    except Exception:
        return []


def setup_tools(db: Any, llm: Any) -> list[BaseTool]:
    """Initialize and assemble agent tools."""
    gmaps_api_key = os.getenv("GPLACES_API_KEY")
    gmaps_client = GoogleMaps(gmaps_api_key) if gmaps_api_key else None

    # 1. FAISS Entity Resolution (Proper Nouns & Addresses)
    addresses = query_as_list(db, "SELECT address FROM core_condobuilding")
    alt_names = query_as_list(db, "SELECT alt_name FROM core_condobuilding")
    entity_texts = list(set(addresses + alt_names))
    
    if entity_texts:
        vector_db = FAISS.from_texts(entity_texts, OpenAIEmbeddings())
        retriever = vector_db.as_retriever(search_kwargs={"k": 5})
        description = (
            "Use to look up exact building names and addresses in the database. "
            "Input is an approximate or colloquial spelling of the proper noun; "
            "output is the closest valid database entity."
        )
        retriever_tool = create_retriever_tool(
            retriever,
            name="search_proper_nouns",
            description=description,
        )
    else:
        retriever_tool = None

    # 2. SQL Toolkit with Safe Gateway
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    raw_tools = toolkit.get_tools()
    
    # Replace default sql_db_query with SafeSQLQueryTool
    safe_sql_tool = SafeSQLQueryTool(db=db)
    tools = [safe_sql_tool]
    for t in raw_tools:
        if t.name != "sql_db_query":
            tools.append(t)

    # 3. Add Geospatial & Proximity Tools
    if retriever_tool:
        tools.append(retriever_tool)
    
    tools.append(GooglePlacesTool())
    tools.append(GeocodingTool(gmaps_client=gmaps_client))
    tools.append(DirectionsTool(gmaps_client=gmaps_client))

    return tools
