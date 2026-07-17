import json
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.data.tulsa_districts import DISTRICT_BOUNDARIES, DISTRICT_REPRESENTATIVES

logger = logging.getLogger(__name__)


class GeocodingService:
    """Simplified service for geocoding addresses and determining city council districts"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.geocodio_api_key = settings.geocodio_api_key

    async def geocode_address(
        self, address: str, city: str = "Tulsa", state: str = "OK"
    ) -> tuple[float, float] | None:
        """
        Geocode an address to latitude/longitude coordinates using Geocodio.

        Args:
            address: Street address
            city: City name (default: Tulsa)
            state: State abbreviation (default: OK)

        Returns:
            Tuple of (latitude, longitude) or None if not found
        """
        try:
            full_address = f"{address}, {city}, {state}"

            # Use Geocodio for geocoding
            coords = await self._geocode_with_geocodio(full_address)
            if coords:
                return coords

            # Return None if geocoding fails instead of default coordinates
            logger.warning(f"Could not geocode address '{address}'")
            return None

        except Exception as e:
            logger.error(f"Error geocoding address '{address}': {str(e)}")

        return None

    async def _geocode_with_geocodio(self, address: str) -> tuple[float, float] | None:
        """Geocode using Geocodio API."""
        try:
            # Check if API key is available
            if not self.geocodio_api_key:
                logger.warning("Geocodio API key not configured, skipping geocoding")
                return None

            url = "https://api.geocod.io/v1.7/geocode"
            params = {
                "q": address,
                "api_key": self.geocodio_api_key,
                "limit": 1,
            }

            # Add proper headers
            headers = {
                "User-Agent": "CivicSparkAI/1.0 (https://github.com/kaizengrowth/CivicSpark_AI)",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers)

                # Check if response is successful
                if response.status_code != 200:
                    logger.error(
                        f"Geocodio API returned status {response.status_code}: {response.text}"
                    )
                    return None

                # Check if response has content
                if not response.text.strip():
                    logger.error("Geocodio API returned empty response")
                    return None

                data = response.json()

                if data.get("results") and len(data["results"]) > 0:
                    result = data["results"][0]
                    location = result.get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")

                    if lat is not None and lng is not None:
                        lat = float(lat)
                        lng = float(lng)

                        # Verify the result is in Tulsa area
                        if self._is_in_tulsa_area(lat, lng):
                            logger.info(
                                f"Successfully geocoded '{address}' to {lat}, {lng}"
                            )
                            return (lat, lng)
                        else:
                            logger.warning(
                                f"Geocoded result outside Tulsa area: {lat}, {lng}"
                            )

        except json.JSONDecodeError as e:
            logger.error(f"Geocodio API returned invalid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Geocodio geocoding error: {str(e)}")

        return None

    def _is_in_tulsa_area(self, lat: float, lon: float) -> bool:
        """Check if coordinates are within Tulsa metropolitan area."""
        # Expanded boundaries for Tulsa metropolitan area to be more inclusive
        tulsa_bounds = {
            "min_lat": 35.7,  # Expanded south
            "max_lat": 36.5,  # Expanded north
            "min_lon": -96.3,  # Expanded west
            "max_lon": -95.6,  # Expanded east
        }

        return (
            tulsa_bounds["min_lat"] <= lat <= tulsa_bounds["max_lat"]
            and tulsa_bounds["min_lon"] <= lon <= tulsa_bounds["max_lon"]
        )

    def determine_district_by_coords(
        self, latitude: float, longitude: float
    ) -> str | None:
        """
        Determine district using real boundary data from GeoJSON.
        Uses point-in-polygon algorithm to check if coordinates fall within district boundaries.
        """
        try:
            # Use real district boundaries if available
            if DISTRICT_BOUNDARIES:
                district = self._point_in_polygon_district_determination(
                    latitude, longitude
                )
                if district:
                    return district

                # If no exact match, try to find the closest district
                closest_district = self._find_closest_district(latitude, longitude)
                if closest_district:
                    logger.info(
                        f"Using closest district {closest_district} for coordinates ({latitude}, {longitude})"
                    )
                    return closest_district

            # No fallback available - return None if no district found
            return None

        except Exception as e:
            logger.error(f"Error determining district by coordinates: {str(e)}")
            return None

    def _point_in_polygon_district_determination(
        self, lat: float, lng: float
    ) -> str | None:
        """
        Determine district using point-in-polygon algorithm with real boundaries.
        """
        for district_name, boundary_coords in DISTRICT_BOUNDARIES.items():
            if self._point_in_polygon(lat, lng, boundary_coords):
                return district_name
        return None

    def _point_in_polygon(
        self, lat: float, lng: float, polygon: list[tuple[float, float]]
    ) -> bool:
        """
        Ray casting algorithm to determine if a point is inside a polygon.
        Improved version that handles edge cases better.
        """
        if not polygon or len(polygon) < 3:
            return False

        n = len(polygon)
        inside = False

        # Handle the case where the polygon is closed (first and last points are the same)
        if polygon[0] == polygon[-1]:
            polygon = polygon[:-1]  # Remove the duplicate closing point
            n = len(polygon)

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            # Check if point is on the boundary
            if (lat == yi and lng == xi) or (lat == yj and lng == xj):
                return True

            # Check if point is on a horizontal edge
            if yi == yj and lat == yi:
                if min(xi, xj) <= lng <= max(xi, xj):
                    return True

            # Check if point is on a vertical edge
            if xi == xj and lng == xi:
                if min(yi, yj) <= lat <= max(yi, yj):
                    return True

            # Ray casting algorithm
            if ((yi > lat) != (yj > lat)) and (
                lng < (xj - xi) * (lat - yi) / (yj - yi) + xi
            ):
                inside = not inside

            j = i

        return inside

    def _find_closest_district(self, lat: float, lng: float) -> str | None:
        """
        Find the closest district by calculating distance to district centroids.
        This is used as a fallback when coordinates don't fall exactly within boundaries.
        """
        # District centroids (approximate center points of each district)
        district_centroids = {
            "District 1": (36.18, -95.95),  # North Tulsa
            "District 2": (36.15, -96.02),  # Northwest
            "District 3": (36.11, -96.02),  # West
            "District 4": (36.07, -95.97),  # Southwest
            "District 5": (36.15, -95.92),  # Central
            "District 6": (36.11, -95.87),  # East
            "District 7": (36.11, -95.92),  # Midtown
            "District 8": (36.03, -95.92),  # South
            "District 9": (36.07, -95.87),  # Southeast
        }

        min_distance = float("inf")
        closest_district = None

        for district_name, (centroid_lat, centroid_lng) in district_centroids.items():
            # Calculate distance using simple Euclidean distance
            distance = ((lat - centroid_lat) ** 2 + (lng - centroid_lng) ** 2) ** 0.5

            if distance < min_distance:
                min_distance = distance
                closest_district = district_name

        # Only return if the closest district is reasonably close (within ~0.1 degrees)
        if min_distance < 0.1:
            return closest_district

        return None

    async def find_district_by_address(self, address: str) -> dict[str, Any]:
        """
        Find city council district for a given address using multiple methods.

        Args:
            address: Street address to lookup

        Returns:
            Dict containing district info, coordinates, and status
        """
        result: dict[str, Any] = {
            "address": address,
            "coordinates": None,
            "district": None,
            "councilor": None,
            "success": False,
            "error": None,
            "method": None,
        }

        try:
            # Try geocoding + coordinate-based district determination
            coords = await self.geocode_address(address)
            if coords:
                result["coordinates"] = {"lat": coords[0], "lng": coords[1]}

                district = self.determine_district_by_coords(coords[0], coords[1])
                if district:
                    result["district"] = district
                    result["councilor"] = DISTRICT_REPRESENTATIVES.get(district, {})
                    result["success"] = True
                    result["method"] = "geocoding"
                    return result

            # If no methods worked
            result["error"] = "Address not found within Tulsa city limits"

        except Exception as e:
            logger.error(f"Error finding district for address '{address}': {str(e)}")
            result["error"] = f"Service error: {str(e)}"

        return result

    def get_all_representatives(self) -> list[dict[str, str]]:
        """Get all district representatives plus mayor."""
        representatives = []

        # Add Mayor
        representatives.append(
            {
                "name": "Monroe Nichols",
                "position": "Mayor",
                "email": "mayor@cityoftulsa.org",
                "phone": "(918) 596-7777",
            }
        )

        # Add all district councilors
        for district, rep_info in DISTRICT_REPRESENTATIVES.items():
            representatives.append(
                {
                    "name": rep_info["name"],
                    "position": rep_info["position"],
                    "email": rep_info["email"],
                    "phone": rep_info.get("phone", ""),
                    "district": district,
                }
            )

        return representatives
