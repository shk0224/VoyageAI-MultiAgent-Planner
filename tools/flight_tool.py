"""VoyageAI flight search: SerpApi Google Flights + interactive terminal.

Install: pip install requests python-dotenv airportsdata
.env: SERPAPI_API_KEY=... (never commit .env)
Run interactive: python -m tools.flight_tool
Import: from tools.flight_tool import search_flights
"""
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlencode

import airportsdata
import requests
from dotenv import load_dotenv

load_dotenv()
AIRPORTS = airportsdata.load('IATA')
SERPAPI_URL = 'https://serpapi.com/search.json'
CITY_AIRPORTS = {
    'atlanta': ['ATL'], 'chicago': ['ORD', 'MDW'],
    'new york': ['JFK', 'LGA', 'EWR'], 'nyc': ['JFK', 'LGA', 'EWR'],
    'los angeles': ['LAX', 'BUR'], 'san francisco': ['SFO', 'OAK'],
    'washington dc': ['DCA', 'IAD', 'BWI'], 'washington': ['DCA', 'IAD', 'BWI'],
    'miami': ['MIA', 'FLL'], 'dallas': ['DFW', 'DAL'],
    'houston': ['IAH', 'HOU'], 'boston': ['BOS'], 'seattle': ['SEA'],
    'orlando': ['MCO'], 'denver': ['DEN'], 'las vegas': ['LAS'],
    'dhaka': ['DAC'], 'kathmandu': ['KTM'], 'karachi': ['KHI'],
    'lahore': ['LHE'], 'islamabad': ['ISB'], 'colombo': ['CMB'],
    'london': ['LHR', 'LGW'], 'tokyo': ['HND', 'NRT'],
}
COUNTRY_ONLY = {'usa', 'united states', 'america', 'bangladesh', 'nepal',
                'pakistan', 'india', 'china', 'sri lanka', 'japan', 'canada',
                'uk', 'united kingdom'}


@dataclass
class Trip:
    origin: str = ''
    destination: str = ''
    outbound_date: str = ''
    return_date: str = ''
    trip_type: str = ''  # 'one-way' or 'round-trip'
    adults: int = 0
    nonstop: bool = False


def airports_for(place):
    """Return known city airports or an exact airport IATA code; never guess a country."""
    name = re.sub(r'\s+', ' ', (place or '').lower().strip(' .,?!'))
    if name in COUNTRY_ONLY:
        return []
    if name in CITY_AIRPORTS:
        return CITY_AIRPORTS[name]
    if len(name) == 3 and name.upper() in AIRPORTS:
        return [name.upper()]
    matches = [code for code, details in AIRPORTS.items()
               if (details.get('city') or '').strip().lower() == name]
    return sorted(matches)[:8]


def parse_route(message):
    """Extract city names from 'from X to Y' or 'X to Y'."""
    s = message.strip()
    m = re.search(r'\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:on|for|with|departing|leaving)\b|[.!?]|$)', s, re.I)
    if not m:
        m = re.search(r'^\s*(.+?)\s+to\s+(.+?)(?=\s+(?:on|for|with|departing)\b|[.!?]|$)', s, re.I)
    return (m.group(1).strip(), m.group(2).strip()) if m else ('', '')


def parse_date_from_text(message):
    """Recognize YYYY-MM-DD and 'November 15, 2026' (English)."""
    iso = re.search(r'\b\d{4}-\d{2}-\d{2}\b', message)
    if iso:
        try:
            return date.fromisoformat(iso.group()).isoformat()
        except ValueError:
            return ''
    months = ('January February March April May June July August September '
              'October November December').split()
    pattern = r'\b(' + '|'.join(months) + r')\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\b'
    m = re.search(pattern, message, re.I)
    if m:
        try:
            return datetime.strptime(f'{m.group(1).title()} {m.group(2)} {m.group(3)}', '%B %d %Y').date().isoformat()
        except ValueError:
            pass
    return ''


def _date_valid(value, minimum=None):
    try:
        d = date.fromisoformat(value)
        return d >= (minimum or date.today())
    except (ValueError, TypeError):
        return False


def _ask_date(prompt, minimum=None):
    while True:
        answer = input(prompt).strip()
        parsed = parse_date_from_text(answer)
        if _date_valid(parsed, minimum):
            return parsed
        print('Please enter a valid future date (YYYY-MM-DD or November 15, 2026).')


def _ask_airport(place, label):
    while True:
        options = airports_for(place)
        if not options:
            print(f'Could not identify airports for {place!r}. Please specify a city or airport code, not just a country.')
            place = input(f'{label} city or airport: ').strip()
            continue
        if len(options) == 1:
            return options[0]
        print(f'{label} airport choices for {place}: {", ".join(options)}')
        choice = input(f'Select an airport (Enter for {options[0]}, or ALL to search all): ').strip().upper()
        if not choice:
            return options[0]
        if choice == 'ALL':
            return ','.join(options)
        if choice in options:
            return choice
        print('Please choose one of the listed airports or ALL.')


def collect_trip(message):
    """Interactive terminal-only questions. Never call from a web request handler."""
    origin, destination = parse_route(message)
    if not origin:
        origin = input('Departure city or airport: ').strip()
    if not destination:
        destination = input('Destination city or airport: ').strip()
    dep = _ask_airport(origin, 'Departure')
    arr = _ask_airport(destination, 'Destination')
    if set(dep.split(',')) & set(arr.split(',')):
        raise ValueError('Departure and destination airports must be different.')
    outbound = parse_date_from_text(message)
    if not _date_valid(outbound):
        outbound = _ask_date('Departure date (YYYY-MM-DD): ')
    print(f'Departure date: {outbound}')
    while True:
        trip_type = input('One-way or round-trip? [o/r]: ').strip().lower()
        if trip_type in ('o', 'one-way', 'one way', 'r', 'round-trip', 'round trip'):
            break
        print('Enter o for one-way or r for round-trip.')
    round_trip = trip_type.startswith('r')
    ret = _ask_date('Return date (YYYY-MM-DD): ', date.fromisoformat(outbound)) if round_trip else ''
    while True:
        try:
            adults = int(input('Number of adult passengers (1-9): ').strip())
            if 1 <= adults <= 9:
                break
        except ValueError:
            pass
        print('Please enter a number from 1 to 9.')
    nonstop = input('Nonstop flights only? [y/N]: ').strip().lower() in ('y', 'yes')
    return Trip(dep, arr, outbound, ret, 'round-trip' if round_trip else 'one-way', adults, nonstop)


def _format_offer(offer, index):
    lines = [f'Option {index} | Price: {offer.get("price", "N/A")} USD | '
             f'Total duration: {offer.get("total_duration", "N/A")} minutes']
    for leg in offer.get('flights') or []:
        d, a = leg.get('departure_airport') or {}, leg.get('arrival_airport') or {}
        lines.append(f'  {leg.get("airline", "Unknown airline")} {leg.get("flight_number", "")}: '
                     f'{d.get("id", "?")} {d.get("time", "?")} -> '
                     f'{a.get("id", "?")} {a.get("time", "?")}')
    layovers = offer.get('layovers') or []
    lines.append(f'  Stops: {len(layovers)}')
    for layover in layovers:
        lines.append(f'    Connection: {layover.get("name", layover.get("id", "?"))} '
                     f'({layover.get("duration", "?")} minutes)')
    if offer.get('extensions'):
        lines.append('  Notes: ' + '; '.join(str(x) for x in offer['extensions'][:3]))
    return '\n'.join(lines)


def search_flight_offers(trip, limit=5, session=None):
    """Search Google Flights via SerpApi. Returns formatted real API data or explicit errors.

    SerpApi prices are search snapshots, not booking guarantees.
    """
    key = os.getenv('SERPAPI_API_KEY')
    if not key:
        return 'Flight search unavailable: SERPAPI_API_KEY is missing from .env.'
    if not (trip.origin and trip.destination and _date_valid(trip.outbound_date)):
        return 'Flight search needs valid origin, destination and a future departure date.'
    if trip.trip_type not in ('one-way', 'round-trip'):
        return 'Flight search needs trip_type: one-way or round-trip.'
    if trip.trip_type == 'round-trip' and not _date_valid(trip.return_date, date.fromisoformat(trip.outbound_date)):
        return 'Round-trip search needs a valid return date.'
    if not (1 <= trip.adults <= 9):
        return 'Please provide 1-9 adult passengers.'
    params = {
        'engine': 'google_flights', 'departure_id': trip.origin,
        'arrival_id': trip.destination, 'outbound_date': trip.outbound_date,
        'type': '1' if trip.trip_type == 'round-trip' else '2',
        'adults': trip.adults, 'currency': 'USD', 'hl': 'en',
        'api_key': key,
    }
    if trip.trip_type == 'round-trip':
        params['return_date'] = trip.return_date
    if trip.nonstop:
        params['stops'] = '1'  # Google Flights API: 1 = nonstop only
    try:
        response = (session or requests).get(SERPAPI_URL, params=params, timeout=35)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return f'Flight search request failed: {exc}'
    if not isinstance(payload, dict):
        return 'Unexpected flight search response.'
    if payload.get('error'):
        return f'Flight search API error: {payload["error"]}'
    offers = (payload.get('best_flights') or []) + (payload.get('other_flights') or [])
    if not offers:
        return ('No flight offers returned for this search. This does not prove that flights '
                'are unavailable. Try other airports, dates or nonstop settings.')
    # The API's flight results can include several airports in a metropolitan area.
    # Keep only offers matching the requested endpoint airport sets.
    origins = set(trip.origin.split(','))
    destinations = set(trip.destination.split(','))
    verified = []
    for offer in offers:
        legs = offer.get('flights') or []
        if not legs:
            continue
        first = (legs[0].get('departure_airport') or {}).get('id')
        last = (legs[-1].get('arrival_airport') or {}).get('id')
        # Round-trip Google Flights first results may contain outbound legs only.
        if first not in origins or last not in destinations:
            continue
        if trip.nonstop and len(legs) != 1:
            continue
        verified.append(offer)
    if not verified:
        return 'API returned no offers matching the selected airports and stop preference.'
    try:
        count = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        count = 5
    header = (f'Google Flights results: {trip.origin} -> {trip.destination} | '
              f'{trip.outbound_date} | {trip.trip_type} | {trip.adults} adult(s)')
    if trip.return_date:
        header += f' | return {trip.return_date}'
    header += '\nPrices are API snapshots, subject to change; not guaranteed bookable.'
    if trip.trip_type == 'round-trip':
        header += ('\nRound-trip search: these may be outbound selections; '
                   'the API may require a second request using departure_token '
                   'to resolve return flights and final total fare.')
    return header + '\n\n' + '\n\n'.join(_format_offer(x, i) for i, x in enumerate(verified[:count], 1))


def search_flights(query, limit=5):
    """Non-interactive API for backend/test.py: never prompts via input().

    Date and origin/destination must be present in the question.
    For full interactive collection run `python -m tools.flight_tool`.
    """
    origin, destination = parse_route(query)
    if not origin or not destination:
        return 'Please specify a route, e.g. Flights from Atlanta to Chicago on November 15, 2026.'
    dep, arr = airports_for(origin), airports_for(destination)
    if not dep or not arr:
        return 'Please specify departure and destination cities or airport codes (not country names).'
    outbound = parse_date_from_text(query)
    if not _date_valid(outbound):
        return 'Please specify a future departure date, e.g. November 15, 2026.'
    # Safe defaults only for non-interactive use; explain them in the output.
    trip = Trip(dep[0], arr[0], outbound, '', 'one-way', 1,
                bool(re.search(r'\bnonstop\b|\bdirect flight\b', query, re.I)))
    result = search_flight_offers(trip, limit)
    return ('Search assumptions: one-way, 1 adult, first matching city airport '
            f'({dep[0]} -> {arr[0]}). For more options use interactive mode.\n\n' + result)


def main():
    print('VOYAGEAI INTERACTIVE FLIGHT SEARCH (SerpApi Google Flights)')
    print('Example: Flights from Atlanta to Chicago on November 15, 2026')
    print('Type exit to quit.\n')
    while True:
        question = input('Your flight question: ').strip()
        if question.lower() in ('exit', 'quit'):
            break
        if not question:
            continue
        try:
            trip = collect_trip(question)
            print('\n' + search_flight_offers(trip) + '\n')
        except (EOFError, KeyboardInterrupt):
            print('\nStopped.')
            break
        except ValueError as exc:
            print(f'Input error: {exc}')


if __name__ == '__main__':
    main()
