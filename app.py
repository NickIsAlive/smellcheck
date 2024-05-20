import streamlit as st
python3 -m pip install folium
from streamlit_folium import folium_static
import pandas as pd
import duckdb
import json
from folium.plugins import Fullscreen
from shapely.geometry import Point, shape
from geopy.distance import geodesic
from streamlit_js_eval import streamlit_js_eval
import logging


# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Load GeoJSON data
with open('gadm41_GRC_3.json', 'r') as f:
    geojson_data = json.load(f)

# Filter for features within the Attica region
attica_data = {
    "type": "FeatureCollection",
    "features": [feature for feature in geojson_data['features'] if feature['properties']['NAME_1'] == 'Attica']
}

# Initialize a simple database to store votes
conn = duckdb.connect(database=':memory:')
conn.execute("CREATE TABLE votes (region_id STRING, vote_option STRING, voter_ip STRING)")

# Preparing a simple DataFrame for counting votes (initialize with no votes)
vote_counts = pd.DataFrame({
    'region_id': [feature['properties']['GID_3'] for feature in attica_data['features']],
    'Yes': [0] * len(attica_data['features']),
    'No': [0] * len(attica_data['features'])
}).set_index('region_id')

def update_vote_counts():
    global vote_counts
    result = conn.execute("SELECT region_id, vote_option, COUNT(*) as count FROM votes GROUP BY region_id, vote_option").fetchdf()
    if not result.empty:
        vote_counts_update = pd.pivot_table(result, values='count', index='region_id', columns='vote_option', fill_value=0).reindex(vote_counts.index, fill_value=0)
        vote_counts.update(vote_counts_update)
    else:
        vote_counts['Yes'] = 0
        vote_counts['No'] = 0

update_vote_counts()

def get_user_location():
    if 'location' not in st.session_state:
        st.session_state.location = streamlit_js_eval(js_expressions='''
            new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(
                    position => resolve([position.coords.latitude, position.coords.longitude]),
                    err => {
                        console.error(err.message);
                        reject(err);
                    }
                );
            })
        ''', key='location_key', want_output=True)
        logging.debug(f"Retrieved user location: {st.session_state.location}")
    else:
        logging.debug(f"User location already in session state: {st.session_state.location}")

    return st.session_state.location if st.session_state.location is not None else [0, 0]
def get_closest_region(user_location):
    user_point = Point(user_location)
    min_distance = None
    closest_region = None

    for feature in attica_data['features']:
        region_shape = shape(feature['geometry'])
        distance = user_point.distance(region_shape)

        if min_distance is None or distance < min_distance:
            min_distance = distance
            closest_region = feature['properties']['GID_3']

    return closest_region

def add_vote(option):
    user_location = get_user_location()
    closest_region = get_closest_region(user_location)
    conn.execute("INSERT INTO votes VALUES (?, ?, ?)", (closest_region, option, 'N/A'))
    update_vote_counts()

def create_map():
    user_location = get_user_location()
    zoom_level = 10  # Zoom level for a selected region
    location = user_location  # Center the map on the user's location
    m = folium.Map(location=location, zoom_start=zoom_level, width=800, height=800)

    # Add fullscreen control to the map
    Fullscreen().add_to(m)

    vote_counts['Dominant'] = (vote_counts['Yes'] > vote_counts['No']).map({True: 'Blue', False: 'Red'})

    folium.GeoJson(
        data=attica_data,
        style_function=lambda feature: {
            'fillColor': vote_counts.loc[feature['properties']['GID_3'], 'Dominant'] if feature['properties']['GID_3'] in vote_counts.index else 'Gray',
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.5
        },
        name='GeoJson Layer'
    ).add_to(m)

    return m
    # Add a marker for the user's location
    if user_location is not None:
        folium.Marker(
            location=user_location,
            popup="Your Location",
            icon=folium.Icon(icon="cloud"),
        ).add_to(m)

    return m
# Define Streamlit columns for layout
col1, col2 = st.columns(2)

user_location = get_user_location()
with col1:
    if user_location is not None:
        st.subheader(f"Please vote (Region: {get_closest_region(user_location)}):")
    else:
        st.subheader("Please vote:")
        if 'voted' not in st.session_state:
            st.session_state.voted = False
        if not st.session_state.voted:
            if st.markdown('<a href="#" class="streamlit-btn streamlit-btn-yes" title="Vote Yes on the proposed laws">Yes</a>', unsafe_allow_html=True):
                add_vote('Yes')
                st.session_state.voted = True
            if st.markdown('<a href="#" class="streamlit-btn streamlit-btn-no" title="Vote No on the proposed laws">No</a>', unsafe_allow_html=True):
                add_vote('No')
                st.session_state.voted = True

map_display = create_map()
folium_static(map_display)

st.markdown("""
<style>
.streamlit-btn {
    display: inline-block;
    padding: 0.5em 1em;
    text-decoration: none;
    border-radius: 3px;
}
.streamlit-btn-yes {
    background: #4CAF50; /* Green */
    color: white;
}
.streamlit-btn-no {
    background: #f44336; /* Red */
    color: white;
}
</style>
""", unsafe_allow_html=True)
