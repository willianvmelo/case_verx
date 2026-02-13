import argparse
from app.crawler_service import CrawlerService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    parser.add_argument("--output", default="equities.csv")
    args = parser.parse_args()

    service = CrawlerService()
    total = service.run(args.region, args.output)

    print(f"{total} ativos coletados")

if __name__ == "__main__":
    main()
