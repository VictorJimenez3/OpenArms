# Can the photographed vessels be matched to manufacturer CAD?

**Finding:** neither vessel is exactly identified. Six plausible product families were checked; no verified public manufacturer STEP/STL/IGES/OBJ/3MF download or reusable CAD license was found. This bounded negative search does not prove no model exists. The original photo-derived models are on main through [PR #23](https://github.com/VictorJimenez3/OpenArms/pull/23), merge `e3c1b9c`; their [parameters, evidence and limitations](../../simulation/models/vessels/measured_2026_11_14/README.md) remain authoritative for this reconstruction.

D1 / issue #19, simulation geometry only. External Account 2 performed primary-source research and inspected all nine user photos; the coordinating agent independently checked the research, Eisco/Globe specifications and asset evidence. No third-party mesh or manufacturer photo was incorporated. No hardware, fixture design or purchase occurred.

## Candidates and conflicting specifications

| Candidate | Manufacturer evidence | What can and cannot be concluded |
| --- | --- | --- |
| Globe / Azlon **BPM0025P** | 25 mL, 5 mL increments, **41.5 mm rim diameter, 51 mm height**. [Globe tapered-beaker table](https://globescientific.com/products/beaker-pp-500ml-tapered-sides-molded-graduations); [SciLabware manufacturer catalog](https://assets.thermofisher.cn/TFS-Assets/ANZ/Catalogs/scilabware-laboratory-glassware-plasticware.pdf), printed p.41. | Close dimensional reference for donor. Rim definition is explicit, but inclusion of the spout is not. No identified mold mark or proof of physical identity. No internal/base dimensions or numerical dimensional tolerance recovered. |
| United Scientific **11110** | New Style/Wide Spout 25 mL, 5 mL interval, **OD × height 34 × 49 mm**. [Manufacturer 2023 laboratory catalog](https://www.unitedsciplus.com/sites/default/files/assets/United%20Scientific%202023%20Laboratory%20catalog.pdf), printed p.5. | Raised scale and large tapered spout fit the general family. “OD” has no located measurement drawing; do not call it confirmed body OD or rim OD. Main product page was blocked; the indexed manufacturer PDF supplied the table. |
| Eisco **CH0137** | Manufacturer describes 25 mL and 5 mL raised graduations; **1.9 in tall, 1.4 in diameter, 1.3 in inner diameter**. [Product](https://www.eiscolabs.com/products/ch0137). | Rounded inch figures correspond to approximately 48, 36 and 33 mm; extra decimal places would invent precision. Product photo resembles the donor's flared rim, triangular spout and rounded base. Diameter elevations and physical maker mark are unresolved. Generic dimensions elsewhere on the same page conflict and have no shown units; excluded. |
| Polylab **11110 Euro Design** | Manufacturer lists **25 mL**, PP, raised graduations and tapered spout. [Product](https://www.polylab.in/product/beakers-euro-design). | Plausible family; no manufacturer length dimensions recovered. Shared 11110 numbering does not prove the same mold/OEM as United. Some live fetches were blocked or timed out; indexed manufacturer content was available. |
| Genfac **RB100** | Manufacturer sheet explicitly gives **75 mm brim diameter × 47.5 mm height**, nominal 100 mL, PP. [Product](https://genfac.com.au/product/100ml-round-sauce-container/); [specification PDF](https://genfac.com.au/wp-content/uploads/2026/02/RB-100-Product-Specification-Sheet.pdf). | Taller than the revised receiver photo estimate (32 mm, plausible 30–35); weak match. No demonstrated match to the bottom embossing. Reseller “80 mm” figures may describe a lid or disagree with the primary sheet; not adopted. Direct source-image retrieval was blocked, so no detailed visual identity claim. |
| Smartivity **My First Science Kit** | Official inventory lists a beaker, flask and two cups. [Kit](https://www.smartivity.in/products/my-first-science-kit). | Context only. No individual vessel dimensions, supplier/mold identity or downloadable vessel CAD recovered. Packaging dimensions and uncalibrated promotional images are not vessel measurements. |

The donor's small molded rectangular mark is not legible enough to identify a maker. Receiver underside markings visibly include `100ml.`, `Reusable`, `5 / PP`, microwave/freezer symbols and molding marks. None identifies an exact supplier. Observed pictograms are not independently tested material/temperature qualifications.

The independent photo audit predates these catalog comparisons. Nominal model geometry was selected from the photo estimates and uncertainty, not forced to a catalog SKU or printed capacity. The best nominal resemblance is a candidate family, not an exact product match.

## CAD and reuse search

Checked exact SKU/family CAD/STEP searches, manufacturer product resources and catalog/download routes for all six families. Globe/Azlon and United expose catalogs; Genfac exposes a product specification PDF. These are not CAD. Eisco exposes public product pictures and registration-gated higher-resolution resources but no verified vessel CAD; no registration was attempted. Polylab and Smartivity yielded no verified model download. No reuse license for manufacturer CAD was located, so none was imported or redistributed.

No numeric geometry tolerance was found in the checked primary specifications. ISO references, graduation increments, nominal capacity and decimal formatting do not supply an OD/height tolerance. Keep model uncertainty from the photographs separate from manufacturer tolerance, which remains unknown.

## Integration implication

The reusable original models can be used now as **estimated geometry**, with the documented interior assumptions. Do not substitute Genfac dimensions or an unverified catalog interior. A direct ruler/caliper session measuring outside heights, circular lip OD, lower-body OD, opening ID, internal depth and donor 25 mL elevation is the shortest path to tighter geometry. For the receiver, the 100 mL underside embossing does not locate a fill level and cannot alone constrain the interior profile.

No static or simulated shape establishes grasp, spill, pour or physical D1 reliability. Fixture CAD remains deferred.
