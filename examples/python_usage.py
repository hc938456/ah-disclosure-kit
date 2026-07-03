from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.services.local_search_service import search_local_document_text

result = ingest_pdf("sample_report.txt", meta={"market": "A", "symbol": "600519", "title": "sample"})
print(result)
print(search_local_document_text("revenue", result["document_id"]))
