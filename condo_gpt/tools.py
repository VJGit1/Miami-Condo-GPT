"""Maps tools and SQL helpers. Charts/maps/tables/PDFs are emitted by the graph.

The LangGraph pipeline does not use a ReAct toolkit. Artifacts come from
render_plan → synthesize via append_artifact.
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from condo_gpt.security.maps_budget import check_maps_budget, current_maps_session, record_maps_call
from condo_gpt.sinks import append_sql_citation
from condo_gpt.sql.gateway import safe_run, validate_sql

_gmaps = None


def _maps_client():
    global _gmaps
    if _gmaps is None:
        from googlemaps import Client as GoogleMaps

        _gmaps = GoogleMaps(os.getenv("GPLACES_API_KEY"))
    return _gmaps


class GeocodingInput(BaseModel):
    address: str = Field(..., description="Address to geocode")


class DirectionsInput(BaseModel):
    origin: str = Field(..., description="The starting point address or coordinates")
    destination: str = Field(
        ..., description="The destination point address or coordinates"
    )


class GeocodingTool(BaseTool):
    name: str = "google_maps_geocoding"
    description: str = "Useful for converting addresses into geographic coordinates."
    args_schema: Type[BaseModel] = GeocodingInput

    def _run(self, address: str) -> str:
        key = current_maps_session()
        ok, msg = check_maps_budget(key)
        if not ok:
            return msg
        try:
            record_maps_call(key)
            geocode_result = _maps_client().geocode(address)
            if geocode_result:
                location = geocode_result[0]["geometry"]["location"]
                return (
                    f"The coordinates for the address {address} are "
                    f"{location['lat']}, {location['lng']}."
                )
            return "Unable to find coordinates for the specified address."
        except Exception as e:
            return f"An error occurred while fetching coordinates: {str(e)}"


class DirectionsTool(BaseTool):
    name: str = "google_maps_directions"
    description: str = (
        "Useful for finding travel distances and directions between two locations."
    )
    args_schema: Type[BaseModel] = DirectionsInput

    def _run(self, origin: str, destination: str) -> str:
        key = current_maps_session()
        ok, msg = check_maps_budget(key)
        if not ok:
            return msg
        try:
            record_maps_call(key)
            directions_result = _maps_client().directions(origin, destination, mode="driving")
            if directions_result:
                distance = directions_result[0]["legs"][0]["distance"]["text"]
                duration = directions_result[0]["legs"][0]["duration"]["text"]
                return (
                    f"The travel distance from {origin} to {destination} is {distance}, "
                    f"and it takes approximately {duration} by car."
                )
            return "Unable to find directions between the specified locations."
        except Exception as e:
            return f"An error occurred while fetching directions: {str(e)}"


class SafeSQLQueryInput(BaseModel):
    query: str = Field(..., description="A PostgreSQL SELECT query to execute")


class SafeSQLQueryTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "sql_db_query"
    description: str = (
        "Execute a PostgreSQL SELECT query against the condo database. "
        "Only SELECT/WITH queries are allowed. DML/DDL is blocked."
    )
    args_schema: Type[BaseModel] = SafeSQLQueryInput
    db: Any = None

    def _run(self, query: str) -> str:
        output, validation = safe_run(self.db, query)
        append_sql_citation(
            {
                "query": validation.sql if validation.ok else query,
                "blocked": not validation.ok,
                "block_reason": validation.error,
            }
        )
        return output


def query_as_list(db, query: str) -> list[str]:
    output, validation = safe_run(db, query, row_limit=5000)
    if not validation.ok:
        return []
    try:
        res = [el for sub in ast.literal_eval(output) for el in sub if el]
        res = [re.sub(r"\b\d+\b", "", string).strip() for string in res]
        return list(set(res))
    except Exception:
        return []


__all__ = [
    "validate_sql",
    "SafeSQLQueryTool",
    "GeocodingTool",
    "DirectionsTool",
    "query_as_list",
]
