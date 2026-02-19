"""Stub MCP server with mock Swiss caselaw data — FastMCP version."""
import json
from mcp.server.fastmcp import FastMCP

MOCK_DECISIONS = [
    {
        "docket_number": "6B_123/2024",
        "court": "bger",
        "decision_date": "2024-03-15",
        "language": "de",
        "title": "Strafrecht; Mietrecht Kündigung",
        "regeste": "Kündigung eines Mietvertrags nach Art. 257d OR. Der Vermieter kann das Mietverhältnis fristlos kündigen, wenn der Mieter mit der Zahlung fälliger Mietzinse im Rückstand ist.",
        "full_text": "[Mock data — production server contains full text of 1M+ decisions]",
        "source_url": "https://www.bger.ch/ext/eurospider/live/de/php/aza/http/index.php?highlight_docid=aza://15-03-2024-6B-123-2024"
    },
    {
        "docket_number": "4A_456/2024",
        "court": "bger",
        "decision_date": "2024-05-20",
        "language": "de",
        "title": "Vertragsrecht; Kaufvertrag",
        "regeste": "Anfechtung eines Kaufvertrags wegen Willensmangel nach Art. 23 ff. OR. Wesentlicher Irrtum über eine Eigenschaft der Kaufsache.",
        "full_text": "[Mock data — production server contains full text of 1M+ decisions]",
        "source_url": "https://www.bger.ch/ext/eurospider/live/de/php/aza/http/index.php?highlight_docid=aza://20-05-2024-4A-456-2024"
    },
    {
        "docket_number": "2C_789/2023",
        "court": "bger",
        "decision_date": "2023-11-08",
        "language": "fr",
        "title": "Droit administratif; Permis de construire",
        "regeste": "Recours contre le refus d'un permis de construire. Examen de la conformité à la zone d'affectation selon l'art. 22 LAT.",
        "full_text": "[Mock data — production server contains full text of 1M+ decisions]",
        "source_url": "https://www.bger.ch/ext/eurospider/live/fr/php/aza/http/index.php?highlight_docid=aza://08-11-2023-2C-789-2023"
    },
]

COURTS = [
    {"id": "bger", "name": "Bundesgericht / Tribunal fédéral", "city": "Lausanne"},
    {"id": "bvger", "name": "Bundesverwaltungsgericht / Tribunal administratif fédéral", "city": "St. Gallen"},
    {"id": "bstger", "name": "Bundesstrafgericht / Tribunal pénal fédéral", "city": "Bellinzona"},
    {"id": "bpatger", "name": "Bundespatentgericht / Tribunal fédéral des brevets", "city": "St. Gallen"},
    {"id": "zh_obergericht", "name": "Obergericht Zürich", "city": "Zürich"},
    {"id": "be_obergericht", "name": "Obergericht Bern", "city": "Bern"},
    {"id": "ag_obergericht", "name": "Obergericht Aargau", "city": "Aarau"},
]

mcp = FastMCP("swiss-caselaw")


@mcp.tool()
def search_decisions(query: str, court: str = None, limit: int = 5) -> str:
    """Search Swiss court decisions by keyword, optionally filtered by court."""
    results = MOCK_DECISIONS
    if court:
        results = [d for d in results if d["court"] == court]
    return json.dumps({"query": query, "total_results": len(results), "results": results[:limit]}, indent=2, ensure_ascii=False)


@mcp.tool()
def get_decision(docket_number: str) -> str:
    """Get a specific Swiss court decision by docket number."""
    found = next((d for d in MOCK_DECISIONS if d["docket_number"] == docket_number), None)
    if found:
        return json.dumps(found, indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Decision {docket_number} not found", "note": "This is a stub server with limited mock data"})


@mcp.tool()
def list_courts() -> str:
    """List all available Swiss courts."""
    return json.dumps({"courts": COURTS}, indent=2, ensure_ascii=False)


@mcp.tool()
def get_statistics() -> str:
    """Get statistics about the decision database."""
    stats = {"total_decisions": 1048576, "courts": len(COURTS), "languages": ["de", "fr", "it", "rm"], "date_range": {"from": "1954-01-01", "to": "2024-12-31"}, "note": "Mock statistics — production server indexes 1M+ real decisions"}
    return json.dumps(stats, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
