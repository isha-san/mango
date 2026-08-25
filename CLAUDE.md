Background
Mangroves and SLR
SLR is expected to proceed at a global average rate of 6mm/year. [FIND A BETTER FIGURE FOR THIS, pref. local to the area of interest]
There aren’t that many tools that take landward migration/ resiliency in the face of SLR into account when determining the best potential sites for restoration/protection of mangroves. Companies requiring carbon storage that is somewhat durable on the scale of decades need to make sure they invest in areas that will be minimally affected by SLR, and where landward migration might be possible. In particular, it’s important for practitioners to quickly eliminate sites that have a high likelihood of landward migration of mangroves being blocked.
Why do mangroves store so much carbon?
Mangroves store up to four times more carbon than land forests because their dense, waterlogged soils lack oxygen. This prevents dead plant matter from rotting quickly. Instead of releasing carbon back i	nto the air as gas, the ecosystem traps it deep underground for centuries. [1, 2, 3]
Is this just a product of the mangroves? Why is the soil dense and waterlogged?
There’s potential for horizontal migration (landward or seaward) in addition to vertical migration, depending on the local geomorphology and hydrology.
The second involves a horizontal movement to occupy adjacent ecosystems including seaward migration and landward migration, possibly due to sediments and organic deposits (Doyle et al. 2010; Lovelock et al. 2010; Langston et al. 2017; Dai et al. 2024). Given the high rates of sea-level rise, which may prevent mangrove growth, horizontal movements are likely to become the most important adaptation mechanism for reducing mangrove loss worldwide because of climate change (Borchert et al. 2018; Dai et al. 2024). - Guerra-Martínez & Rioja-Nieto
Factors influencing landward migration
Among the areas where mangroves already live, how do we figure out which ones are most likely to support landward migration? 
Factors that may limit landward migration include physiography, mangrove extent, anthropogenic development, and other topographical barriers along the coast (Doyle et al. 2010; Enwright et al. 2015). - G&R
Human development. Distance from farms, aquaculture ponds, seawalls, other infrastructure.
Is it possible that seawalls might help in the short term if they lead to greater sediment accumulation on the seaward side?
Topographical barriers that reduce hydrological connectivity. 
levees
roads
dikes
seawalls
filled wetlands
urban development
altered drainage
Amount of future suitable elevation. “Elevation envelope.”
Let’s say that the mangrove landward migration rate is X, and RSLR is projected to be Y in that location. Then, will RSLR catch up to mangroves?Based on this threshold, how much available area is there? How does that translate to a score?
Another approach: let’s say that the mangroves in a particular area tend to live +1 ft above the sea level at that region. How much landward area falls within the elevation range that could support mangroves in 2050/2100? 
Natural topographical barriers. 
How do you identify a prohibitively steep incline?
Sediment accretion rate. More accretion = more likelihood of migration? 
This one is a little bit less supported when it comes to horizontal migration, so I’m going to leave this one be for now, unless it turns out that it’s a major predictor of migration. 
Adjacent wetland area. 
Adjacent tropical forest area. 
Our study revealed that landward migration occurs spatially through the displacement of adjacent vegetation and land uses upslope and upstream. Displaced ecosystems correspond to other wetlands, tropical forests (for this study, they include tropical forests and floodplain grasslands known locally as savannas), and areas with anthropogenic development such as agricultural land. -G+R
Shade tolerance of the dominant mangrove species. Not all adjacent forested/wetland ecosystems are hospitable to mangrove seedlings. 
Hydrological connectivity. 
Data pipeline
If there are a limited number of geographic regions in which I will have access to all of the high-res data that I need, what’s the best way to approach data gathering? Ideally, practitioners shouldn’t limited to one geographic region when they use my tool. 

First, try to find global datasets (probably possible for coastal DEM data, for example). 
Then, prioritize the selected regions when seeking out less consistently sought-out data such as human infrastructure. Mexico has an excellent national high-resolution DEM. India has a potentially excellent 10 m product. Indonesia has DEMNAS at ~8 m. Brazil is much more fragmented, with high-resolution LiDAR/topobathy available for particular states/projects rather than one obvious nationwide 5–10 m DEM.
Deciding geographical scope
How are CDR (and other) practitioners currently doing mangrove restoration? What about conservation? 
Where are the biggest mangrove restoration/conservation hotspots right now? 
Where might a large company looking for nature-based CDR attempt to deploy mangrove restoration and conservation? 
The biggest global hotspots
The clearest concentration is Southeast Asia. Asia contains ~40% of the world's remaining mangroves, and the Global Mangrove Alliance estimates 3,927 km² of restorable mangroves in the region—about 47% of the global Mangrove Breakthrough restoration target.
A 2025 global cost study similarly found that the largest low-cost restoration potential is concentrated in Indonesia, Brazil, Mexico, Myanmar, and India.
I'd therefore think about the landscape roughly like this:


Region
Countries I'd watch
Why a CDR company might care
Southeast Asia
🇮🇩 Indonesia, 🇵🇭 Philippines, 🇲🇲 Myanmar, 🇻🇳 Vietnam, 🇹🇭 Thailand, 🇰🇭 Cambodia
Enormous mangrove area + large restoration opportunity + high carbon stocks
South Asia
🇮🇳 India, 🇧🇩 Bangladesh
Huge mangrove systems, substantial restoration potential, strong climate/biodiversity co-benefits
Latin America
🇲🇽 Mexico, 🇧🇷 Brazil, 🇨🇴 Colombia
Very large restorable area; relatively strong conservation institutions in some areas
West/East Africa
🇬🇳 Guinea-Bissau, 🇸🇳 Senegal, 🇬🇲 Gambia, 🇸🇱 Sierra Leone, 🇲🇿 Mozambique, 🇰🇪 Kenya
Huge ecological importance and restoration opportunity; often significant community/livelihood angle
Northern Australia
🇦🇺 Australia
Excellent biophysical conditions and enormous intact mangrove systems, but less obvious restoration opportunity
Caribbean/Central America
🇨🇺 Cuba, 🇲🇽 Mexico, 🇵🇦 Panama, 🇨🇴 Colombia, etc.
High biodiversity/coastal-protection value and significant restoration opportunities

The latest GMA restoration-potential analysis identified 8,183 km² of potentially restorable mangrove across 110 countries/territories. Indonesia alone had >2,000 km², with large areas also in Mexico, Australia and Myanmar.
And Southeast Asia isn't just historically important: a 2026 analysis found that 12% of Southeast Asia's mangroves are in "very high conservation risk" hotspots, while 16% are in "very high restoration opportunity" areas.
If I were a large company saying:
"We want to spend $50–200M on mangrove-based carbon removal/conservation over the next 10 years."
I would probably start with Indonesia, Mexico, Brazil, India, the Philippines, and selected West African countries, rather than simply looking for the places with the most mangroves.
DEM data
I’ve never worked with GIS data before. DEMs are stored as .tif files. Had to learn about .tif files. 

How are these datasets updated? → not a question for v1
For my tool, I want a software design that will automatically include data updates into its forecast.
Python backend - obviously large number of data analysis packages. 
I ideally want to take advantage of public APIs with (esp global) DEM data so that: 
I save on storage costs
I don’t have to manually upload or build a pipeline for uploading global DEM data as it’s updated by institutions
Milestone 1 - build a pipeline for model development with coastal DEM data. Ie, pull in global and regional coastal DEM data into a notebook somewhere for further analysis. 
Data sources: 

Country
Higher-res national/regional DEM
Resolution
Easy public API/download?
What I'd do
🇵🇭 Philippines
NAMRIA IfSAR
5 m
❌ Not really open/self-service
Use if you can obtain access; otherwise Copernicus
🇻🇳 Vietnam
National/aerial DEM
~10 m in some datasets
⚠️ Mixed
Investigate regional access
🇮🇳 India
Survey of India DEM
10 m nationally; finer products in some areas
⚠️ Access-controlled
Very promising if accessible
🇮🇩 Indonesia
DEMNAS
~8 m
⚠️ Public but access workflow varies
Strong candidate
🇲🇽 Mexico
INEGI LiDAR DTM
5 m / 1.5 m
✅ Relatively accessible
Definitely use
🇧🇷 Brazil
Local/state LiDAR
~1–10 m
⚠️ Fragmented
Use selectively

Human infrastructure data
I’m interested in both land use and physical infrastructure that might act as a barrier to migration. For this, there appear to be a large number of well-maintained datasets that I can use. 
Land use datasets: 
Dynamic World - 10 m resolution, global, near-real-time land cover.
Crops, flooded vegetation and built area are covered. 
https://dynamicworld.app/
Continually updated (every 2-5 days)
GHSL (Global Human Settlement Layer)

Physical infrastructure datasets: need to be high-res enough that I can tell if landward migration is blocked by a specific road, levee, or seawall. 
OpenStreetMap for roads
Global Dam Watch

National datasets
Brazil - MapBiomas - specific categorization of land cover
Mexico - INEGI Uso del Suelo y Vegetación
India - ISRO/NRSC Bhuvan
Indonesia - KLHK land-cover products
Philippines - NAMRIA land-cover products

The ideal dataset stack: 
Variable
Dataset
Resolution
Elevation
Best regional DEM / Copernicus
5–30 m
Current land use
Dynamic World
10 m
Historical water
JRC Global Surface Water
30 m
Infrastructure
OpenStreetMap
vector
River barriers
Global Dam Watch
vector
Human pressure
Global Human Modification
1 km



Building the model
I could use ML, but the benefit of analyzing each feature individually is explainability to practitioners. 
For the initial design of this product, since I’m not a mangrove scientist (and only have college-level biology background, pretty much), my goal is to make this tool as transparent as possible - ie, the features I’m using to determine suitability for mangrove restoration and conservation should be visible to practitioners, so that they can ultimately make the call on whether to invest money into a feasibility survey. 
Papers
Read Woodroffe et al. (2016), Mangrove Sedimentation and Response to Relative Sea-Level Rise. Why elevation and sediment dynamics matter.
Read Gilman et al. (2008), Threats to mangroves from climate change and adaptation options.
Read Krauss et al. (2014), How mangrove forests adjust to rising sea level. - general overview of how mangroves contribute to soil elevation under SLR scenarios. Heavily focused on how plant anatomy and physiology shapes the environment. https://www.sciencedirect.com/science/article/pii/S1569843226003778
https://www.sciencedirect.com/science/article/pii/S2197562023000155?via%3Dihub - aquaculture ponds and cropland limit landward migration of mangroves.
Guerra-Martínez & Rioja-Nieto, https://link.springer.com/article/10.1007/s10113-026-02598-8 - mangrove migration in the Yucatan peninsulta, 1984-2024
Doyle et al, predicting the retreat of mangrove forests in the Gulf of Mexico - https://linkinghub.elsevier.com/retrieve/pii/S0378112709007658
Boon et al 2011 - a group of scientists did an analysis of the amount of suitable land for landward migration under an 80cm SLR scenario https://www.semanticscholar.org/paper/Mangroves-and-Coastal-Saltmarsh-of-Victoria-%3A-and-Boon-Allen/041d43e98ee6a80a2e495deeffd180808cc2bbe4 


