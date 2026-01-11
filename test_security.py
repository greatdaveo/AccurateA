"""
Security Testing Script - Clean Version
Validates Rate Limiting, IP Blocking, CORS, and Security Headers.
"""
import requests
import time
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

BASE_URL = "http://localhost:8000"

def print_success(msg):
    print(f"{Fore.GREEN}[SUCCESS] {msg}{Style.RESET_ALL}")

def print_error(msg):
    print(f"{Fore.RED}[FAILURE] {msg}{Style.RESET_ALL}")

def print_info(msg):
    print(f"{Fore.CYAN}[INFO] {msg}{Style.RESET_ALL}")

def test_rate_limiting():
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print("TEST 1: Rate Limiting")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    print_info("Sending 65 requests (limit is 60/min)...")
    responses = []
    blocked_at = None

    for i in range(65):
        try:
            response = requests.get(f"{BASE_URL}/api/dashboard/summary", timeout=5)
            responses.append(response.status_code)

            if response.status_code == 429 and blocked_at is None:
                blocked_at = i + 1
                print_info(f"Rate limit triggered at request {blocked_at}")
        except requests.exceptions.RequestException as e:
            print_error(f"Connection error: {e}")
            break

    total_429 = responses.count(429)
    if 429 in responses:
        print_success(f"Rate limiting active. Blocked {total_429} requests.")
    else:
        print_error("Rate limiting inactive - no 429 responses received.")

def test_suspicious_paths():
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print("TEST 2: Suspicious Path Blocking")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    suspicious_paths = [
        "/admin", "/.env", "/wp-admin",
        "/phpmyadmin", "/.git/config", "/xmlrpc.php"
    ]
    blocked_count = 0

    for path in suspicious_paths:
        response = requests.get(f"{BASE_URL}{path}", timeout=2)
        if response.status_code == 403:
            print_success(f"Blocked: {path}")
            blocked_count += 1
        else:
            print_error(f"Allowed: {path} (Status: {response.status_code})")

    if blocked_count == len(suspicious_paths):
        print_success("All suspicious patterns correctly blocked.")

def test_ip_blocking():
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print("TEST 3: IP Blocking Strategy")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    print_info("Triggering IP block via suspicious path...")
    requests.get(f"{BASE_URL}/wp-admin")

    time.sleep(1)
    print_info("Verifying if IP is restricted for valid paths...")
    response = requests.get(f"{BASE_URL}/health")

    if response.status_code == 403:
        print_success("IP successfully restricted from entire API.")
    else:
        print_error("IP restriction failed - valid paths still accessible.")

def test_cors():
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print("TEST 4: CORS Configuration")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    print_info("Testing unauthorized origin...")
    response = requests.get(
        f"{BASE_URL}/health",
        headers={"Origin": "https://evil-hacker-site.com"}
    )

    allow_origin = response.headers.get("access-control-allow-origin")
    if not allow_origin or allow_origin != "https://evil-hacker-site.com":
        print_success("Unauthorized origin rejected.")
    else:
        print_error("Unauthorized origin accepted - CORS vulnerability detected.")

def test_security_headers():
    print(f"\n{Fore.YELLOW}{'=' * 60}")
    print("TEST 5: Security Headers")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    response = requests.get(f"{BASE_URL}/health")
    required = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
    }

    for header, expected in required.items():
        actual = response.headers.get(header)
        if actual == expected:
            print_success(f"{header}: {actual}")
        else:
            print_error(f"{header}: {actual if actual else 'MISSING'} (Expected: {expected})")

if __name__ == "__main__":
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print("  SECURITY TEST SUITE - VALIDATION START  ")
    print(f"{'=' * 60}{Style.RESET_ALL}")

    try:
        test_suspicious_paths()
        test_rate_limiting()
        test_ip_blocking()
        test_cors()
        test_security_headers()
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}\n  TESTS COMPLETED\n{'=' * 60}")
    except Exception as e:
        print(f"\n{Fore.RED}Critical error during execution: {e}")