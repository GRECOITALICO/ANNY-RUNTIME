import sys
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: interceptor.py <output_file> <url>")
        sys.exit(1)

    output_file = sys.argv[1]
    url = sys.argv[2]

    # We only write the first URL we receive, or we overwrite it.
    # colab-mcp polls and sends the same URL repeatedly if we don't connect.
    with open(output_file, "w") as f:
        f.write(url)

if __name__ == "__main__":
    main()
