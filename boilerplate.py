marker_boilerplate = """"var marker = new google.maps.Marker({
position: {lat: markerData.lat, lng: markerData.lng},
map: map,
title: markerData.name + ' - ' + markerData.address, 
label: markerData.name
});
"""

holding_period_boilerplate = """

WITH sale_deltas AS (
    SELECT 
        cs1.condo_unit_id, 
        cs1.closing_date AS current_closing_date, 
        cs2.closing_date AS previous_closing_date,
        (cs1.closing_date - cs2.closing_date) AS delta_days
    FROM 
        core_condosale cs1
    JOIN 
        core_condosale cs2 
    ON 
        cs1.condo_unit_id = cs2.condo_unit_id 
    WHERE 
        cs1.closing_date > cs2.closing_date
        AND cs1.blacklist = FALSE
        AND cs2.blacklist = FALSE
        AND cs2.closing_date = (
            SELECT MAX(cs3.closing_date)
            FROM core_condosale cs3
            WHERE cs3.condo_unit_id = cs1.condo_unit_id
            AND cs3.closing_date < cs1.closing_date
            AND cs3.blacklist = FALSE
        )
        AND cs1.condo_unit_id IN (
            SELECT id 
            FROM core_condounit 
            WHERE blacklist = FALSE 
            AND building_id IN (
                SELECT id 
                FROM core_condobuilding 
                WHERE market_id = (
                    SELECT id FROM core_condomarket WHERE name = 'Brickell'
                )
            )
        )
)
SELECT 
    AVG(delta_days) AS average_delta
FROM 
    sale_deltas;



"""

two_bed_holding_period_boilerplate = """


WITH sale_deltas AS (
    SELECT 
        cs1.condo_unit_id, 
        cs1.closing_date AS current_closing_date, 
        cs2.closing_date AS previous_closing_date,
        (cs1.closing_date - cs2.closing_date) AS delta_days
    FROM 
        core_condosale cs1
    JOIN 
        core_condosale cs2 
    ON 
        cs1.condo_unit_id = cs2.condo_unit_id 
    WHERE 
        cs1.closing_date > cs2.closing_date
        AND cs1.blacklist = FALSE
        AND cs2.blacklist = FALSE
        AND cs2.closing_date = (
            SELECT MAX(cs3.closing_date)
            FROM core_condosale cs3
            WHERE cs3.condo_unit_id = cs1.condo_unit_id
            AND cs3.closing_date < cs1.closing_date
            AND cs3.blacklist = FALSE
        )
        AND cs1.condo_unit_id IN (
            SELECT id 
            FROM core_condounit 
            WHERE blacklist = FALSE 
            AND beds = 2
            AND building_id IN (
                SELECT id 
                FROM core_condobuilding 
                WHERE market_id = (
                    SELECT id FROM core_condomarket WHERE name = 'Brickell'
                )
            )
        )
)
SELECT 
    AVG(delta_days) AS average_delta
FROM 
    sale_deltas;


"""

javascript_map_boilerplate = """
<script>
function initMap() {
    var locations = [
        {lat: LATITUDE_NUMBER, lng: LONGITUDE_NUMBER, label: "MARKER_LABEL"}
    ];

    var map = new google.maps.Map(document.getElementById("map"), {
        zoom: 13,
        center: {lat: LATITUDE_NUMBER, lng: LONGITUDE_NUMBER}
    });

    var bounds = new google.maps.LatLngBounds();
    locations.forEach(function(location) {
        var marker = new google.maps.Marker({
            position: {lat: location.lat, lng: location.lng},
            map: map,
            label: location.label
        });
        bounds.extend(marker.getPosition());
    });
    if (locations.length > 0) {
        map.fitBounds(bounds);
    }
}
initMap();
</script>
<div id="map" style="height: 400px; width: 100%;"></div>
"""

building_marker_format_boilerplate = "{lat: LATITUDE_NUMBER, lng: LONGITUDE_NUMBER, label: 'ALT_NAME - STREET_ADDRESS'}"

school_marker_format_boilerplate = "{lat: LATITUDE_NUMBER, lng: LONGITUDE_NUMBER, label: 'SCHOOL_NAME'}"
