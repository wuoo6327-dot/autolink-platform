# Overseas buyer search intent map · 2026-10-12

This is a content routing map, not a ranking or search-volume claim. One landing page serves each distinct intent; query variants do not generate near-duplicate URLs. The model and brand counts are recomputed from current database rows and their content gates.

| Buyer query or cluster | Intent | Reviewed destination | Publication rule |
| --- | --- | --- | --- |
| China Car Export; Buy Cars from China | Understand the sourcing process | `/guide/trade-process` | Existing English guide; no promise of supply |
| Cars Exported from China | Explore China-market model references | `/trade/models` and `/guide/vehicle-sourcing` | Model directory remains separate from inventory |
| Chinese Car Suppliers; China Vehicle Exporters; China New Car Suppliers | Find actual public suppliers | `/trade/suppliers` | Only published supplier records appear |
| Chinese Cars Wholesale | Discover actual listings and request quantity | `/trade/vehicles` | No blanket wholesale-stock claim |
| Geely Monjaro China Export | Research the exact model and then inquire | `/trade/models/geely-monjaro-2026` | Reviewed English model reference; no FOB price |
| BYD China Export Supplier | Compare BYD references and look for approved offers | `/trade/brands/byd` | Brand research is not manufacturer authorization |
| Changan CS75 Plus China | Research the China-market configuration | `/trade/models/changan-catalog-1` | Existing reviewed English model page |
| China FOB Car Quotation | Understand the required quote fields | `/guide/trade-process` | A seller must provide the actual price and named term |
| Chinese Cars for Middle East Importers | Region-specific buyer due diligence | `/guide/middle-east-importers` | English-only guide; import compliance and stock are separate checks |
| Chinese vehicle sourcing for African importers | Compare country-specific buyer checks and verified supply | `/guide/african-importers` | English guide; no continent-wide import or stock claim |

## Market content decisions

- **Middle East:** one English sourcing guide is implemented. It asks buyers to specify their destination country and independently verify import, registration and vehicle requirements. It does not claim that any named model is eligible there.
- **Africa:** one English buyer guide now distinguishes a model reference, an approved supplier listing and destination-country import checks. Its Nigeria context links to the U.S. Commercial Service and its Kenya steering/inspection prompt links to the Kenya Revenue Authority. It does not claim that any linked China-market model qualifies in either country. Nigeria, Kenya, Ghana and Morocco country pages remain research briefs until each has original, sourced content.
- **Central Asia:** research brief only. A future page should distinguish destination-country documentation and vehicle specifications from a China-market reference; do not reuse the Middle East text with country names changed.
- **Southeast Asia:** research brief only. Different national import frameworks and steering conventions require country-level research and real supplier evidence before an indexable page.

The nine-language interface remains available. Editorial model and brand approval remains English only. The Middle East guide has an Arabic RTL draft at `?lang=ar` that is `noindex` until a qualified reviewer approves its terminology and market fit. Other unreviewed language variants return a readable `noindex` fallback. The indexed guides use English canonical and `x-default` only.
