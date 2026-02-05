import requests
import json

url = "http://localhost:8000/simulate"

payload = {
    "latitude": 5.6037,
    "longitude": -0.1870,
    "capacity_kw": 10.0,
    "tilt": 15,
    "year": 2023
}

print(f"Sending request to {url}...")
print(f"Payload: {json.dumps(payload, indent=2)}")

try:
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print("\nSuccess!")
        print(f"Annual Energy: {data['results']['annual_energy_kwh']:.2f} kWh")
        print(f"First 5 Monthly Values: {data['results']['monthly_energy'][:5]}")
    else:
        print(f"\nError {response.status_code}: {response.text}")

except requests.exceptions.ConnectionError:
    print("\nError: Could not connect to API. Is it running?")
