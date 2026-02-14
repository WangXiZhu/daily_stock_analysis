import requests

code = 'hk09988'
url = f"http://qt.gtimg.cn/q={code}"
print(f"Testing {url}")

try:
    response = requests.get(url)
    print(f"Status: {response.status_code}")
    print(f"Content: {response.text}")
    
    content = response.text
    if '"' in content:
        data = content.split('"')[1]
        fields = data.split('~')
        print(f"Fields count: {len(fields)}")
        for i, f in enumerate(fields):
            print(f"{i}: {f}")

except Exception as e:
    print(f"Failed: {e}")
