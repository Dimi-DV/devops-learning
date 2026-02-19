import requests

urls = ["https://httpbin.org/get",
    "https://google.com",
    "https://httpbin.org/status/404",
    "https://httpbin.org/status/500",
    ]

for url in urls:
    response = requests.get(url)
    ms = response.elapsed.total_seconds() * 1000
    status = "UP" if response.status_code < 300 else "DOWN"
    print(f"{status} | {response.status_code} | {ms:.0f} ms | {url}")