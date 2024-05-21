
import streamlit as st
import folium
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
conn.execute("CREATE TABLE votes (region_id STRING, vote_option INT, voter_ip STRING)")

# Preparing a simple DataFrame for counting votes (initialize with no votes)
vote_counts = pd.DataFrame({
    'region_id': [feature['properties']['GID_3'] for feature in attica_data['features']],
    '1': [0] * len(attica_data['features']),
    '2': [0] * len(attica_data['features']),
    '3': [0] * len(attica_data['features']),
    '4': [0] * len(attica_data['features']),
    '5': [0] * len(attica_data['features']),
    'Average': [0.0] * len(attica_data['features'])
}).set_index('region_id')

def update_vote_counts():
    global vote_counts
    result = conn.execute("SELECT region_id, vote_option, COUNT(*) as count FROM votes GROUP BY region_id, vote_option").fetchdf()
    if not result.empty:
        vote_counts_update = pd.pivot_table(result, values='count', index='region_id', columns='vote_option', fill_value=0).reindex(vote_counts.index, fill_value=0)
        vote_counts.update(vote_counts_update)
        for region_id in vote_counts.index:
            total_votes = sum(vote_counts.loc[region_id, str(i)] for i in range(1, 6))
            if total_votes > 0:
                average = sum(i * vote_counts.loc[region_id, str(i)] for i in range(1, 6)) / total_votes
                vote_counts.at[region_id, 'Average'] = average
    else:
        for i in range(1, 6):
            vote_counts[str(i)] = 0
        vote_counts['Average'] = 0.0

update_vote_counts()

def get_user_location():
    if 'location' not in st.session_state:
        st.session_state.location = streamlit_js_eval(js_expressions='''new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                position => resolve([position.coords.latitude, position.coords.longitude]),
                err => reject(err)
            );
        });''', key='get_location', success='resolve')
    return st.session_state.location

def get_closest_region(user_location):
    user_point = Point(user_location[1], user_location[0])
    closest_region = None
    min_distance = float('inf')
    for feature in attica_data['features']:
        region_shape = shape(feature['geometry'])
        distance = user_point.distance(region_shape)
        if distance < min_distance:
            min_distance = distance
            closest_region = feature['properties']['GID_3']
    return closest_region

def add_vote(vote_option):
    user_ip = st.experimental_get_query_params().get('ip', ['unknown'])[0]
    region_id = get_closest_region(st.session_state.location)
    conn.execute("INSERT INTO votes (region_id, vote_option, voter_ip) VALUES (?, ?, ?)", (region_id, vote_option, user_ip))
    update_vote_counts()

def create_map():
    m = folium.Map(location=[37.9838, 23.7275], zoom_start=10)
    folium.TileLayer('cartodbpositron').add_to(m)
    
    folium.GeoJson(
        data=attica_data,
        style_function=lambda feature: {
            'fillColor': 'blue' if vote_counts.loc[feature['properties']['GID_3'], 'Average'] == 0 else 'yellow' if vote_counts.loc[feature['properties']['GID_3'], 'Average'] < 3 else 'green',
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.5
        },
        name='GeoJson Layer'
    ).add_to(m)
    
    return m

# Define Streamlit columns for layout
col1, col2 = st.columns(2)

user_location = get_user_location()
with col1:
    if user_location is not None:
        st.subheader(f"How safe do you feel cycling on public roads? (Region: {get_closest_region(user_location)}):")
        if 'voted' not in st.session_state:
            st.session_state.voted = False
        if not st.session_state.voted:
            vote = st.slider("Rate from 1 to 5", min_value=1, max_value=5)
            if st.button("Submit Vote"):
                add_vote(vote)
                st.session_state.voted = True
    else:
        st.subheader("How safe do you feel cycling on public roads?")
        st.text("Unable to get your location.")

map_display = create_map()
with col2:
    folium_static(map_display)
