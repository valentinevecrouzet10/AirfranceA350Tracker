import json
import math
from pathlib import Path

import airportsdata
import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title='Air France A350 Tracker', page_icon='✈️', layout='wide')
DATA = Path(__file__).parent / 'progression.json'
# Vols indicatifs relevés dans les horaires A350 Air France : ne garantissent pas le type à une date donnée.
FLIGHTS = '''AF178,CDG,MEX
AF174,CDG,MEX
AF179,MEX,CDG
AF175,MEX,CDG
AF198,CDG,BKK
AF199,BKK,CDG
AF134,CDG,BKK
AF133,BKK,CDG
AF282,CDG,HND
AF281,HND,CDG
AF162,CDG,HND
AF163,HND,CDG
AF484,CDG,GIG
AF485,GIG,CDG
AF410,CDG,GIG
AF409,GIG,CDG
AF422,CDG,BOG
AF423,BOG,CDG
AF718,CDG,DSS
AF719,DSS,CDG
AF460,CDG,GRU
AF459,GRU,CDG
AF188,CDG,HKG
AF185,HKG,CDG
AF264,CDG,ICN
AF267,ICN,CDG
AF990,CDG,JNB
AF995,JNB,CDG
AF356,CDG,YYZ
AF357,YYZ,CDG
AF470,CDG,MRU
AF473,MRU,CDG
AF418,CDG,MRU
AF417,MRU,CDG
AF510,CDG,CAI
AF509,CAI,CDG
AF588,CDG,SJO
AF589,SJO,CDG
AF412,CDG,EZE
AF411,EZE,CDG
AF26,CDG,LAX
AF12,CDG,JFK
AF11,JFK,CDG
AF60,CDG,BOS
AF61,BOS,CDG
AF706,CDG,ABJ
AF705,ABJ,CDG
AF68,CDG,PHX
AF69,PHX,CDG
AF258,CDG,SGN
AF253,SGN,CDG
AF208,CDG,MNL
AF209,MNL,CDG
AF56,CDG,LAS
AF66,CDG,ORD
AF76,CDG,SEA
AF592,CDG,CKY
AF585,CKY,CDG
AF28,CDG,LAX
AF26,LAX,PPT
AF27,PPT,LAX
AF872,CDG,CPT
AF871,CPT,CDG
AF406,CDG,SCL
AF401,SCL,CDG
AF474,CDG,PTY
AF475,PTY,CDG
AF86,CDG,DFW
AF87,DFW,CDG
AF96,CDG,MCO
AF97,MCO,CDG
AF374,CDG,YVR
AF375,YVR,CDG
AF52,CDG,IAD
AF53,IAD,CDG
AF860,CDG,LFW
AF861,LFW,CDG
AF594,CDG,NKC
AF537,NKC,CDG
AF866,CDG,ABV
AF866,ABV,NDJ
AF866,NDJ,CDG
AF70,CDG,EWR
AF71,EWR,CDG
AF972,CDG,NBJ
AF971,NBJ,CDG
AF218,CDG,BOM
AF217,BOM,CDG
AF696,CDG,JIB
AF669,JIB,CDG
AF148,CDG,LOS
AF149,LOS,CDG
AF446,CDG,SXM
AF445,SXM,CDG
AF684,CDG,RUH
AF685,RUH,CDG
AF530,NKC,CKY
AF57,LAS,CDG
AF67,ORD,CDG
AF77,SEA,CDG
AF28,LAX,PPT
AF29,PPT,LAX'''

@st.cache_data
def airports():
    return airportsdata.load('IATA')

@st.cache_data
def initial_flights():
    return pd.DataFrame([line.split(',') for line in FLIGHTS.splitlines()], columns=['vol','depart','arrivee'])

def load_progress():
    try:
        return json.loads(DATA.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def save_progress(progress):
    DATA.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')

def great_circle(lat1, lon1, lat2, lon2, n=70):
    a1, o1, a2, o2 = map(math.radians, (lat1, lon1, lat2, lon2))
    p = (math.cos(a1)*math.cos(o1), math.cos(a1)*math.sin(o1), math.sin(a1))
    q = (math.cos(a2)*math.cos(o2), math.cos(a2)*math.sin(o2), math.sin(a2))
    omega = math.acos(max(-1, min(1, sum(x*y for x,y in zip(p,q)))))
    coords = []
    for i in range(n+1):
        t = i/n
        if omega < 1e-8:
            v = p
        else:
            v = tuple(math.sin((1-t)*omega)/math.sin(omega)*x + math.sin(t*omega)/math.sin(omega)*y for x,y in zip(p,q))
        coords.append((math.degrees(math.atan2(v[2], math.hypot(v[0],v[1]))), math.degrees(math.atan2(v[1],v[0]))))
    # Coupe les lignes au passage de la ligne de changement de date.
    segments = [[coords[0]]]
    for previous, current in zip(coords, coords[1:]):
        if abs(current[1]-previous[1]) > 180:
            segments.append([])
        segments[-1].append(current)
    return [s for s in segments if len(s)>1]

st.title('✈️ Air France A350 — Flight Tracker')
st.caption('Journal personnel des vols simulés • A350-900 (A359) • routes fréquentes et occasionnelles, selon la saison et la date')
with st.sidebar:
    st.header('Catalogue')
    st.markdown('[Consulter iFlySchedules](https://iflyschedules.com/routefinder) — choisir **Air France** et **A359**.')
    st.markdown('[Vérifier les lignes A350 sur AeroLOPA](https://www.aerolopa.com/routes/af/airbus-a350-900)')
    uploaded = st.file_uploader('Importer un CSV (vol,depart,arrivee)', type='csv')
    st.caption('Les routes sont regroupées par paire d’aéroports, dans les deux sens. Les anciennes validations sont conservées.')
    search = st.text_input('Rechercher une route, un vol ou un aéroport')
    status = st.selectbox('Afficher', ['Tous les vols', 'À effectuer', 'Effectués'])
    show_map = st.checkbox('Afficher la carte', value=True)
    st.caption('Les validations sont enregistrées localement dans progression.json.')

flights = initial_flights().copy()
if uploaded:
    try:
        extra = pd.read_csv(uploaded, dtype=str)
        extra.columns = [c.strip().lower() for c in extra.columns]
        if not {'vol','depart','arrivee'}.issubset(extra.columns):
            st.error('Colonnes requises : vol,depart,arrivee')
        else:
            extra = extra[['vol','depart','arrivee']].dropna()
            for c in extra.columns:
                extra[c] = extra[c].str.strip().str.upper()
            flights = pd.concat([flights, extra], ignore_index=True).drop_duplicates()
    except Exception as exc:
        st.error(f'CSV illisible : {exc}')

# Une route = une paire d'aéroports, indépendamment du sens et du numéro AF.
flights['id'] = flights.apply(lambda r: '|'.join(sorted([r['depart'], r['arrivee']])), axis=1)
progress = load_progress()
# Compatibilité avec les validations de l'ancienne version (identifiants AFxxx|AAA|BBB).
for old_id, done in list(progress.items()):
    parts = old_id.split('|')
    if done and len(parts) == 3:
        route_id = '|'.join(sorted(parts[1:]))
        progress[route_id] = True
flights = flights.groupby('id', as_index=False).agg(
    depart=('depart', lambda v: 'CDG' if 'CDG' in set(v) else sorted(v)[0]),
    arrivee=('arrivee', lambda v: next((x for x in v if x != 'CDG'), sorted(v)[0])),
    vol=('vol', lambda v: ', '.join(sorted(set(v))))
)
# Reconstruire le sens affiché à partir de la paire canonique.
for idx, row in flights.iterrows():
    a, b = row['id'].split('|')
    flights.at[idx, 'depart'] = 'CDG' if 'CDG' in (a,b) else a
    flights.at[idx, 'arrivee'] = (b if a == 'CDG' else a) if 'CDG' in (a,b) else b
flights['effectue'] = flights['id'].map(lambda x: bool(progress.get(x, False)))
valid = airports()
flights = flights[flights['depart'].isin(valid) & flights['arrivee'].isin(valid)].copy()
flights['trajet'] = flights['depart'] + ' → ' + flights['arrivee']
if search:
    flights = flights[flights[['vol','depart','arrivee','trajet']].apply(lambda col: col.str.contains(search.upper(), case=False, regex=False)).any(axis=1)]
if status == 'À effectuer':
    flights = flights[~flights['effectue']]
elif status == 'Effectués':
    flights = flights[flights['effectue']]

all_ids = set(flights['id'])
completed = sum(bool(progress.get(x, False)) for x in all_ids)
c1,c2,c3 = st.columns(3)
c1.metric('Routes du catalogue', len(all_ids))
c2.metric('Effectués', completed)
c3.metric('Progression', f'{100*completed/max(len(all_ids),1):.0f} %')

if show_map:
    world = folium.Map(location=[25, 5], zoom_start=2, tiles='OpenStreetMap', world_copy_jump=False)
    seen_airports = set()
    for flight in flights.itertuples():
        a,b = valid[flight.depart], valid[flight.arrivee]
        color = '#16a34a' if flight.effectue else '#dc2626'
        popup = f'{flight.vol} : {flight.depart} → {flight.arrivee} — {"Effectué" if flight.effectue else "À faire"}'
        for segment in great_circle(a['lat'],a['lon'],b['lat'],b['lon']):
            folium.PolyLine(segment, color=color, weight=2.5, opacity=0.7, tooltip=popup).add_to(world)
        for code, airport in [(flight.depart,a),(flight.arrivee,b)]:
            if code not in seen_airports:
                folium.CircleMarker([airport['lat'],airport['lon']], radius=4, color='#1d4ed8', fill=True, fill_opacity=0.9, tooltip=f'{code} — {airport.get("city", "")}').add_to(world)
                seen_airports.add(code)
    components.html(world.get_root().render(), height=560, scrolling=False)
    st.caption('🟢 Vert : effectué  |  🔴 Rouge : à faire  |  🔵 Point : aéroport. Les lignes représentent des orthodromies, pas des plans de vol réels.')

st.subheader('Valider tes routes')
st.caption('Une route ne compte qu’une fois, même avec plusieurs numéros de vol ou dans les deux sens. Coche « Effectué », puis enregistre.')
edit = flights[['id','vol','depart','arrivee','effectue']].rename(columns={'vol':'Numéros AF','depart':'Départ','arrivee':'Arrivée','effectue':'Effectué'})
changed = st.data_editor(edit, hide_index=True, use_container_width=True, disabled=['id','Numéros AF','Départ','Arrivée'], column_config={'id':None,'Effectué':st.column_config.CheckboxColumn('Effectué')}, key='editor')
if st.button('💾 Enregistrer les validations', type='primary'):
    for row in changed.itertuples(index=False):
        progress[row.id] = bool(getattr(row, 'Effectué'))
    save_progress(progress)
    st.rerun()

st.download_button('Exporter la progression (JSON)', json.dumps(progress, ensure_ascii=False, indent=2), file_name='progression_a350.json', mime='application/json')
st.info('Catalogue enrichi à partir des lignes A350 listées par AeroLOPA (novembre 2026). Certaines liaisons sont occasionnelles ou saisonnières, et peuvent être opérées en Boeing ou A330 à d’autres dates. Ce n’est pas une synchronisation automatique iFlySchedules.')
