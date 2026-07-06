import urllib.request
import sys
import json

def check_health():
    url = "http://localhost:8000/health"
    try:
        response = urllib.request.urlopen(url, timeout=5)
        status_code = response.getcode()
        
        if status_code == 200:
            data = json.loads(response.read().decode())
            print(f"Health Check PASSED: status is {data.get('status')}")
            sys.exit(0)
        else:
            print(f"Health Check FAILED: Status code {status_code}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Health Check FAILED: Could not connect to API. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_health()
