#!/usr/bin/env python3
"""
log_analyzer.py - Apache/Nginx Access Log Parser
Day 5 - Week 1 DevOps Learning

Usage:
    python3 log_analyzer.py access.log
    python3 log_analyzer.py access.log --output report.json
"""

import argparse   # standard library - parses command-line arguments
import json       # standard library - converts Python objects to JSON format
import re         # standard library - regular expressions for pattern matching
import sys        # standard library - access to system-level stuff like sys.exit()
from collections import Counter  # special dict that counts occurrences automatically


# ─────────────────────────────────────────────
# REGEX PATTERN for Apache Combined Log Format
# Each () group captures one field from the log line
# ─────────────────────────────────────────────
LOG_PATTERN = re.compile(
    r'(\S+)'          # group 1: IP address (\S+ = one or more non-whitespace chars)
    r'\s-\s-\s'       # literal " - - " (ident and auth fields, always empty dashes)
    r'\[([^\]]+)\]'   # group 2: timestamp inside brackets ([^\]]+ = anything not a ])
    r'\s"(\S+)\s'     # group 3: HTTP method (GET, POST, etc.) inside the quoted request
    r'(\S+)\s'        # group 4: URL path (/docs, /api/v1/products, etc.)
    r'([^"]+)"\s'     # group 5: HTTP protocol (HTTP/1.1, HTTP/2.0, etc.)
    r'(\d{3})\s'      # group 6: status code (exactly 3 digits)
    r'(\S+)'          # group 7: response size in bytes (or "-" if none)
)


def parse_arguments():
    """
    Sets up and reads command-line arguments.
    argparse automatically generates --help text and validates input.
    """
    parser = argparse.ArgumentParser(
        description="Parse Apache/Nginx access logs and output a JSON report"
    )

    # positional argument - required, no -- prefix
    parser.add_argument(
        "logfile",
        help="Path to the access log file (e.g. access.log)"
    )

    # optional argument - has a default value if not provided
    parser.add_argument(
        "--output",
        default=None,   # None means print to terminal instead of file
        help="Optional: save JSON report to this file (e.g. --output report.json)"
    )

    return parser.parse_args()
    # After this call, args.logfile and args.output are available


def parse_log_file(filepath):
    """
    Opens the log file and parses each line using our regex pattern.
    Returns a list of dicts, one per successfully parsed line.
    Skips and counts malformed lines instead of crashing.
    """
    parsed_lines = []   # will hold one dict per valid log line
    malformed = 0       # count lines we couldn't parse

    try:
        # 'r' = read mode, encoding='utf-8' handles special characters
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()   # remove leading/trailing whitespace and \n

                if not line:          # skip empty lines
                    continue

                match = LOG_PATTERN.match(line)

                if match:
                    # match.group(n) extracts the nth capture group from regex
                    ip, timestamp, method, url, protocol, status, size = match.groups()

                    parsed_lines.append({
                        "ip": ip,
                        "timestamp": timestamp,
                        "method": method,       # GET, POST, DELETE, etc.
                        "url": url,             # /docs, /api/v1/products, etc.
                        "protocol": protocol,   # HTTP/1.1, HTTP/2.0, etc.
                        "status": status,       # "200", "404", "500" (string not int)
                        "size": size            # bytes, or "-" if no body
                    })
                else:
                    malformed += 1
                    # Only warn about first 5 bad lines to avoid flooding output
                    if malformed <= 5:
                        print(f"  Warning: malformed line {line_number}: {line[:80]}",
                              file=sys.stderr)   # stderr = error output, separate from stdout

    except FileNotFoundError:
        # This exception fires when the file path doesn't exist
        print(f"Error: file not found: '{filepath}'", file=sys.stderr)
        sys.exit(1)   # exit code 1 = error (0 = success, any other number = error)

    except PermissionError:
        # This fires when the file exists but you don't have read access
        print(f"Error: permission denied reading '{filepath}'", file=sys.stderr)
        sys.exit(1)

    if malformed > 5:
        print(f"  Warning: {malformed} total malformed lines skipped", file=sys.stderr)

    return parsed_lines


def analyze(parsed_lines):
    """
    Takes the list of parsed log dicts and computes all our statistics.
    Returns a single dict with all results - this is what becomes our JSON report.
    """
    total = len(parsed_lines)

    if total == 0:
        # Return early with empty report rather than crashing on division/empty data
        return {"error": "No valid log lines found", "total_requests": 0}

    # Extract each field into its own list for analysis
    # List comprehension: [expression for item in list] - builds a new list
    ips = [line["ip"] for line in parsed_lines]
    urls = [line["url"] for line in parsed_lines]
    statuses = [line["status"] for line in parsed_lines]
    methods = [line["method"] for line in parsed_lines]

    # Counter is a dict subclass that counts hashable objects
    # Counter(["a", "b", "a"]) → {"a": 2, "b": 1}
    ip_counts = Counter(ips)
    url_counts = Counter(urls)
    status_counts = Counter(statuses)
    method_counts = Counter(methods)

    # .most_common(n) returns list of (item, count) tuples sorted by count descending
    # e.g. [("192.168.1.1", 171), ("10.0.2.34", 146), ...]
    top_ips = [
        {"ip": ip, "requests": count}
        for ip, count in ip_counts.most_common(10)
    ]

    top_urls = [
        {"url": url, "requests": count}
        for url, count in url_counts.most_common(10)
    ]

    # Build status code distribution as a clean dict
    # {"200": 750, "404": 84, "301": 45, ...}
    status_distribution = dict(status_counts.most_common())

    # Count specific status code groups
    errors_4xx = sum(count for status, count in status_counts.items()
                     if status.startswith("4"))   # 400, 401, 403, 404, etc.

    errors_5xx = sum(count for status, count in status_counts.items()
                     if status.startswith("5"))   # 500, 502, 503, etc.

    success_2xx = sum(count for status, count in status_counts.items()
                      if status.startswith("2"))   # 200, 201, 204, etc.

    return {
        "summary": {
            "total_requests": total,
            "unique_ips": len(set(ips)),          # set() removes duplicates
            "unique_urls": len(set(urls)),
            "success_2xx": success_2xx,
            "client_errors_4xx": errors_4xx,
            "server_errors_5xx": errors_5xx,
        },
        "http_methods": dict(method_counts.most_common()),
        "status_distribution": status_distribution,
        "top_10_ips": top_ips,
        "top_10_urls": top_urls,
    }


def output_report(report, output_path=None):
    """
    Converts the report dict to formatted JSON and either:
    - prints it to the terminal (if no output path given)
    - saves it to a file (if --output was specified)
    """
    # json.dumps() = convert Python dict to JSON string
    # indent=2 = pretty print with 2-space indentation
    json_output = json.dumps(report, indent=2)

    if output_path:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_output)
            print(f"Report saved to: {output_path}")
        except PermissionError:
            print(f"Error: cannot write to '{output_path}'", file=sys.stderr)
            sys.exit(1)
    else:
        # print() goes to stdout by default
        print(json_output)


def main():
    """
    Entry point - orchestrates the full pipeline:
    parse args → read file → analyze → output
    """
    args = parse_arguments()

    print(f"Parsing: {args.logfile}", file=sys.stderr)

    # Step 1: read and parse the log file
    parsed_lines = parse_log_file(args.logfile)

    print(f"Parsed {len(parsed_lines)} valid lines", file=sys.stderr)

    # Step 2: analyze the parsed data
    report = analyze(parsed_lines)

    # Step 3: output the JSON report
    output_report(report, args.output)


# This block only runs when the script is executed directly
# If another script imports this file, main() won't auto-run
# This is standard Python convention
if __name__ == "__main__":
    main()
