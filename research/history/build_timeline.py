"""Build the reviewed timeline. All paths stay within research/history/."""
import csv
from pathlib import Path
S={
'lm_post':('https://www.londonmuseum.org.uk/collections/london-stories/penny-post-sparked-letter-writing-revolution/','The Penny Post sparked a letter-writing revolution | London Museum'),
'bpma':('https://www.postoffice.alectritton.co.uk/page/rowlandhill/',"Rowland Hill's Postal Reforms | British Postal Museum & Archive (legacy-site mirror)"),
'eb_hill':('https://en.wikisource.org/wiki/1911_Encyclop%C3%A6dia_Britannica/Hill%2C_Sir_Rowland','1911 Encyclopaedia Britannica: Hill, Sir Rowland'),
'upu':('https://www.upu.int/en/News/2012/2/The-Penny-Black-finally-at-the-UPU','The Penny Black finally at the UPU'),
'us_rates':('https://about.usps.com/who/profile/history/domestic-letter-rates-1792-1863.htm','Rates for Domestic Letters, 1792-1863 | USPS'),
'si_growth':('https://postalmuseum.si.edu/the-growth-of-the-postal-service','The Growth of the Postal Service | National Postal Museum'),
'us_stamps':('https://about.usps.com/who/profile/history/stamps-postcards.htm','Stamps and Postcards | USPS'),
'si_stamps':('https://postalmuseum.si.edu/finding-guide/1847-federal-postage-stamp-correspondence','1847 Federal Postage Stamp Correspondence | National Postal Museum'),
'us_delivery':('https://about.usps.com/who/profile/history/universal-service-postal-monopoly-history.htm','Universal Service and the Postal Monopoly: A Brief History | USPS'),
'si_delivery':('https://postalmuseum.si.edu/exhibition/fifteen-objects-that-changed-postal-history/changing-mail-delivery','Changing Mail Delivery | National Postal Museum'),
'us_rural':('https://about.usps.com/who/profile/history/rural-free-delivery.htm','Rural Free Delivery | USPS'),
'si_rates':('https://postalmuseum.si.edu/us-domestic-letter-rates','U.S. Domestic Letter Rates | National Postal Museum'),
'rmg_opt':('https://www.rmg.co.uk/collections/objects/rmgc-object-159409','View of the Telegraph erected on the Admiralty Office Charing Cross in Feby. 1796 | Royal Museums Greenwich'),
'signals':('https://www.royalsignalsmuseum.co.uk/early-communications-pre-corps/','Early communications – pre Corps | Royal Signals Museum'),
'smg_cw':('https://collection.sciencemuseumgroup.org.uk/objects/co32899/cooke-and-wheatstone-five-needle-telegraph','Cooke and Wheatstone five-needle telegraph | Science Museum Group'),
'lm_cw':('https://www.londonmuseum.org.uk/collections/v/object-730102/telegraph-four-needle-telegraph/','Telegraph, four-needle telegraph | London Museum'),
'liffen':('https://www.tandfonline.com/doi/abs/10.1179/175812110X12714133353911','The Introduction of the Electric Telegraph in Britain, a Reappraisal of the Work of Cooke and Wheatstone'),
'loc_morse':('https://www.loc.gov/item/mcc00054/','First telegraph message, 24 May 1844 | Library of Congress'),
'si_morse':('https://www.si.edu/object/what-hath-god-wrought-telegraph-message%3Anmah_713485','What Hath God Wrought Telegraph Message | Smithsonian'),
'lm_tele':('https://www.londonmuseum.org.uk/collections/london-stories/how-telegraph-took-off-victorian-london/','How the telegraph took off in Victorian London | London Museum'),
'bt_archive':('https://www.bt.com/about/bt/our-history/bt-archives/major-collections','Major collections | BT Group Archives'),
'act1885':('https://www.legislation.gov.uk/ukpga/Vict/48-49/58/pdfs/ukpga_18850058_en.pdf','Telegraph Act 1885'),
'illmag':('https://victorianweb.org/periodicals/englishillustrated/6.html','Post-Office Parcels and Telegraphs | The English Illustrated Magazine (Victorian Web transcription)'),
'loc_cable':('https://guides.loc.gov/this-month-in-business-history/august/first-transatlantic-telegraph-cable','First Transatlantic Telegraph Cable Sent | Library of Congress'),
'iet1858':('https://www.theiet.org/membership/library-and-archives/the-iet-archives/archives-highlights/the-first-transatlantic-telegraph-cable-1858','The first transatlantic telegraph cable 1858 | IET Archives'),
'state_cable':('https://history.state.gov/milestones/1866-1898/telegraph','The Transatlantic Telegraph Cable | Office of the Historian, U.S. Department of State'),
'met_cable':('https://www.metmuseum.org/art/collection/search/383832','The Atlantic Telegraph Cable Fleet Assembled at Berehaven | Metropolitan Museum of Art'),
'loc_phone':('https://www.loc.gov/everyday-mysteries/categories/technology/item/who-is-credited-with-inventing-the-telephone/','Who is credited with inventing the telephone? | Library of Congress'),
'si_phone':('https://avpreservation.si.edu/object/nmah_689864','Alexander Graham Bell Experimental Telephone | Smithsonian'),
'nps_exchange':('https://home.nps.gov/subjects/nationalhistoriclandmarks/site-of-the-first-telephone-exchange.htm','Site of the First Telephone Exchange | National Park Service'),
'uconn':('https://library.uconn.edu/location/asc/about/25-for-25-celebrating-twenty-five-years-of-collecting/the-worlds-first-telephone-directory/',"The World's First Telephone Directory | UConn Library"),
'bt_phone':('https://www.bt.com/bt-plc/assets/documents/about-bt/our-history/bt-archives/information-sheets-and-timelines/private-and-municipal-telephone-companies.pdf','Private and municipal telephone companies | BT Heritage & Archives'),
'exchange_paper':('https://www.tandfonline.com/doi/full/10.1080/17581206.2026.2622702','Close connections: the architecture of telephone exchange buildings'),
'smg_phone':('https://journal.sciencemuseum.ac.uk/article/troublesome-telephony/','Troublesome telephony: how users and non-users shaped the development of early British exchange telephony'),
'hansard_phone':('https://api.parliament.uk/historic-hansard/written-answers/1912/nov/04/telephone-service','Telephone Service | Hansard, 4 November 1912'),
'loc_phone_timeline':('https://guides.loc.gov/chronicling-america-telephone-invention','Invention of the Telephone: Topics in Chronicling America | Library of Congress'),
'hagley':('https://www.hagley.org/research/news/hagley-vault/date-january-25-1915-alexander-graham-bell','On this date ... January 25 ... 1915 ... Alexander Graham Bell | Hagley'),
'census_phone':('https://www2.census.gov/library/working-papers/2025/comm/bell-and-the-1900-census.pdf','Alexander Graham Bell and the 1900 Census | U.S. Census Bureau'),
'ucd_phone':('https://itspubs.ucdavis.edu/download_pdf.php?id=267','Prospecting the Environmental Impacts of Telecommunications: A Study of Telework | UC Davis'),
'stockton':('https://heritage.stockton.gov.uk/articles/stories/stockton-where-passenger-railways-began/','Stockton: Where Passenger Railways Began | Stockton Heritage'),
'historic_rail':('https://historicengland.org.uk/whats-new/research/a-brief-overview-of-the-stockton-and-darlington-railway/','A Brief Overview of the Stockton & Darlington Railway | Historic England'),
'smg_lmrail':('https://collection.sciencemuseumgroup.org.uk/people/cp29532/liverpool-and-manchester-railway','Liverpool & Manchester Railway | Science Museum Group'),
'asme':('https://www.asme.org/about-asme/engineering-history/landmarks/263-liverpool-manchester-railway-site-rainhill','Liverpool Manchester Railway & Site of Rainhill Trials | ASME'),
'parl_rail':('https://www.parliament.uk/about/living-heritage/transformingsociety/transportcomms/roadsrail/overview/fireandsteam/','Fire and steam | UK Parliament'),
'nrm_mania':('https://blog.railwaymuseum.org.uk/parliamentary-papers-and-railway-mania/','Parliamentary papers and Railway Mania | National Railway Museum'),
'archives_rail':('https://www.archives.gov/milestone-documents/pacific-railway-act','Pacific Railway Act (1862) | National Archives'),
'loc_rail':('https://guides.loc.gov/chronicling-america-golden-spike','Golden Spike (1869): Topics in Chronicling America | Library of Congress'),
'mariners':('https://catalogs.marinersmuseum.org/object/CL20201','The British Steamer Sirius | The Mariners Museum'),
'ieee_steam':('https://spectrum.ieee.org/crossing-the-atlantic','Crossing the Atlantic | IEEE Spectrum'),
'lm_gas':('https://www.londonmuseum.org.uk/collections/london-stories/gas-lamps-illuminated-london/','How gas lamps illuminated London | London Museum'),
'gas_museum':('https://www.nationalgasmuseum.org.uk/discover/the-early-days/','The early days | National Gas Museum'),
'gas_lamps':('https://www.nationalgasmuseum.org.uk/lamp-locations/','Lamp locations | National Gas Museum'),
'soane':('https://www.soane.org/exhibitions/georgian-illuminations/lighting',"Artificial light in Georgian England | Sir John Soane's Museum"),
'maryland':('https://msa.maryland.gov/megafile/ecp/26/040/html/0300.html','Baltimore street lighting history | Maryland State Archives (page heading UNVERIFIED)'),
'aoghs':('https://aoghs.org/technology/manufactured-gas/','Illuminating Gaslight | American Oil & Gas Historical Society'),
'menlo':('https://www.menloparkmuseum.org/history','Thomas Edison and Menlo Park | Thomas Edison Center at Menlo Park'),
'nps_edison':('https://www.nps.gov/edis/learn/historyculture/edison-biography.htm?simple=True','Edison Biography | Thomas Edison National Historical Park'),
'si_light':('https://americanhistory.si.edu/lighting/19thcent/promo19.htm','Lighting A Revolution: 19th Century Promotion | Smithsonian'),
'nps_timeline':('https://www.nps.gov/edis/learn/kidsyouth/timeline-of-edison-and-his-inventions.htm','Timeline | Thomas Edison National Historical Park'),
'si_pearl':('https://www.americanhistory.si.edu/lighting/scripts/s19c.htm','Lighting A Revolution: Script for 19th Century Promotion | Smithsonian'),
'godalming':('https://www.godalmingmuseum.co.uk/articles/electricity','Godalming & Electricity | Godalming Museum'),
'iet_power':('https://www.theiet.org/media/11265/selected-landmarks-in-power.pdf','Selected landmarks in the history of Electricity Generation, Distribution, Utilisation | IET'),
}
rows=[]
def add(i,d,c,y,m,event,meaning,a,b,confidence='high'):
 rows.append([i,d,c,y,m,event,'Inference: '+meaning,*S[a],*S[b],confidence])
add('UK_POST_BASELINE','communication','UK',1800,'','Baseline c.1800–1839: inland postage charged by distance and sheets; recipient commonly paid. This row is a period anchor, not a reform date.','Postal cost can impede contact; local penny posts already exist.','lm_post','bpma')
add('UK_POST_FRANKING','communication','UK',1840,1,'10 January: free parliamentary franking abolished with Uniform Penny Post; before this MPs and peers could frank limited letters free and the privilege was abused.','Pre-reform access to a patron can matter for correspondence.','lm_post','bpma')
add('UK_FOURPENNY_POST','communication','UK',1839,12,'5 December: transitional uniform fourpenny postage introduced.','Do not assign the whole of 1839 to the old rate regime.','bpma','eb_hill')
add('UK_PENNY_POST','communication','UK',1840,1,'10 January: Uniform Penny Post introduced; basic prepaid inland rate one penny per half ounce.','Lower distance-related postal cost; timing and withholding remain possible obstacles.','bpma','eb_hill')
add('UK_PENNY_BLACK','communication','UK',1840,5,'Penny Black valid from 6 May; sale began 1 May. DISAGREEMENT: UPU calls 6 May the issue date; BPMA distinguishes sale from validity.','A stamp is evidence of prepaid correspondence, not evidence of successful delivery.','bpma','upu','high; date terminology differs')
add('US_POST_1845','communication','US',1845,7,'1 July: single-letter unit becomes half ounce; 5 cents up to 300 miles and 10 cents beyond.','Lower postage and weight charging change the cost of contact.','us_rates','si_growth')
add('US_STAMPS_1847','communication','US',1847,7,'1 July: first federal general-issue U.S. postage stamps available; earlier local provisionals are distinct.','Prepayment becomes easier; stamps do not yet imply compulsory prepayment.','us_stamps','si_stamps')
add('US_POST_1851','communication','US',1851,7,'1 July: half-ounce letter up to 3000 miles costs 3 cents prepaid or 5 unpaid; over 3000 miles 6 prepaid or 10 unpaid.','Prepayment and distance both still matter.','us_rates','si_growth')
add('US_POST_PREPAY','communication','US',1855,4,'1 April: domestic letter prepayment required; stamp-only prepayment followed in January 1856.','Distinguish paying in advance from obligatory use of stamps.','us_rates','si_growth')
add('US_POST_UNIFORM_1863','communication','US',1863,7,'1 July: uniform domestic letter rate 3 cents per half ounce regardless of distance.','Separates physical distance from the basic domestic letter price.','si_rates','us_delivery')
add('US_CITY_DELIVERY','communication','US',1863,7,'1 July: free city delivery established in qualifying cities; not universal household delivery.','Urban access improves before rural access.','us_delivery','si_delivery')
add('US_RURAL_DELIVERY','communication','US',1896,10,'1 October: experimental Rural Free Delivery begins in West Virginia; permanent service status follows in 1902.','Rural remoteness remains plausible long after city delivery starts.','us_rural','si_delivery')
add('UK_OPTICAL_TELEGRAPH','communication','UK',1796,2,'Murray shutter telegraph adopted by Admiralty in 1796; February Admiralty installation depicted in contemporary print. Pre-1800 precedent.','Telegraph need not mean electricity; visual signaling depends on visibility.','rmg_opt','signals')
add('UK_CW_1837','communication','UK',1837,'','Cooke–Wheatstone practical electric telegraph patented in 1837.','Technical feasibility precedes broad public access.','smg_cw','lm_cw')
add('UK_CW_1839','communication','UK',1839,'','Demonstration line installed on Great Western Railway between Paddington and West Drayton. DISAGREEMENT: London Museum cable record describes five-needle adoption; its instrument record and Liffen identify four-needle instruments.','Railway signaling and public interpersonal messaging must be distinguished.','lm_cw','liffen','high for line/year; instrument descriptions differ')
add('US_MORSE_1844','communication','US',1844,5,'24 May: Morse formally demonstrates Washington–Baltimore telegraph line.','Rapid messaging begins on a particular corridor, not everywhere.','loc_morse','si_morse')
add('ATLANTIC_CABLE_1858','communication','both',1858,8,'First transatlantic telegraph cable connects Ireland and Newfoundland; fails within weeks.','Do not code 1858 as continuous reliable Atlantic connectivity; endpoints are not in the U.S.','loc_cable','iet1858')
add('ATLANTIC_CABLE_1866','communication','both',1866,7,'Durable transatlantic cable service established; second working cable recovered in September.','Fast Atlantic news becomes feasible but tariffs and access remain constraints.','state_cable','met_cable')
add('UK_TELEGRAPH_STATE','communication','UK',1870,2,'5 February: Post Office takes over inland private telegraph networks; not all international cable companies.','More coordinated inland messaging infrastructure; evaluate access locally.','lm_tele','bt_archive','high for year/scope; February day corroborated by EB1911 in README')
add('UK_SIXPENNY_TELEGRAM','communication','UK',1885,10,'1 October: inland minimum telegram charge cut to sixpence for twelve words including addresses; halfpenny per additional word.','Cost falls but word limits and addressed delivery still constrain messages.','act1885','illmag')
add('US_BELL_PATENT','communication','US',1876,3,'7 March: Bell granted U.S. patent 174465; intelligible speech experiment on 10 March is a separate event.','Patent date is a technological hinge, not a household adoption threshold.','loc_phone','si_phone')
add('US_PHONE_EXCHANGE','communication','US',1878,1,'28 January: commercial telephone exchange opens in New Haven.','Switching allows subscribers to contact multiple others locally.','nps_exchange','uconn')
add('UK_PHONE_EXCHANGE','communication','UK',1879,8,'August: public exchange opens at 36 Coleman Street, London. DISAGREEMENT: BT phone-books leaflet says seven initial subscribers; architectural study says eight.','Initial access is tiny and geographically restricted.','bt_phone','exchange_paper','high for date/place; initial count disputed')
add('UK_PHONE_1912','communication','UK',1912,1,'1 January: Post Office acquires National Telephone Company system; municipal exceptions mean this is not literally all UK service.','Institutional consolidation is not proof of universal access.','hansard_phone','smg_phone')
add('US_PHONE_TRANSCO','communication','US',1915,1,'25 January: ceremonial inauguration of transcontinental telephony; distinguish earlier engineering tests from this public milestone.','Long-distance voice contact becomes possible for connected users.','loc_phone_timeline','hagley')
add('US_PHONE_DIFFUSION_1920','communication','US',1920,'','Estimated 35 percent of U.S. households have telephone service. Two publications corroborate the figure but may share underlying Census/FCC data.','Even late in the corpus most households lack service; avoid universal-availability assumptions.','census_phone','ucd_phone','medium; corroborating publications not independent measurements')
add('UK_STOCKTON_DARLINGTON','mobility','UK',1825,9,'27 September: Stockton & Darlington Railway opens with steam-hauled inaugural train; ordinary early operations also use horses.','An early regional railway hinge, not instant national passenger connectivity.','stockton','historic_rail')
add('UK_LIVERPOOL_MANCHESTER','mobility','UK',1830,9,'15 September: ceremonial opening of Liverpool & Manchester Railway; regular passengers follow on 17 September and goods on 1 December.','Scheduled intercity steam travel becomes a plausible setting and deadline mechanism.','smg_lmrail','asme')
add('UK_RAILWAY_MANIA','mobility','UK',1844,'','Railway Mania c.1844–1846; parliamentary authorisations peak in 1846 and construction follows.','Use a rollout window; authorisation does not equal operational travel access.','parl_rail','nrm_mania')
add('US_TRANSCONTINENTAL_RAIL','mobility','US',1869,5,'10 May: Central Pacific and Union Pacific joined at Promontory Summit, Utah Territory.','Overland travel times fall on connected routes; cost and last-mile travel remain.','archives_rail','loc_rail')
add('ATLANTIC_STEAM_1838','mobility','both',1838,4,'Sirius and Great Western make Atlantic steam crossings in April 1838. Arrival-day accounts vary (22/23 April); no day-level hinge asserted. Earlier steam-assisted crossings existed.','More predictable Atlantic passage is a candidate mechanism; do not equate steam with no weather delays.','mariners','ieee_steam','high for month/year; day descriptions vary')
add('UK_PALL_MALL_GAS','lighting','UK',1807,'','Winsor demonstrates gas street lighting in Pall Mall in 1807. Reports differ on January versus June demonstrations; month left blank.','Local night visibility changes before widespread street or domestic gas provision.','lm_gas','gas_museum','high for year; demonstration-month accounts differ')
add('UK_GAS_ROLLOUT','lighting','UK',1813,'','Following 1812 charter, Westminster public gasworks opens in 1813; Westminster Bridge lit by December; London has over 4000 gas lamps by the 1820s.','Treat 1810s–1820s as urban rollout rather than a nationwide cutoff.','gas_museum','soane')
add('US_BALTIMORE_GAS','lighting','US',1817,2,'7 February: first municipal gas street lamp lit in Baltimore; 1816 refers to company authorisation and demonstrations.','Municipal street illumination is distinct from domestic lighting.','maryland','aoghs')
add('US_EDISON_LAMP','lighting','US',1879,10,'Edison develops a practical carbon-filament incandescent lamp in October; public Menlo Park demonstration follows in December. No claim that Edison invented all electric lighting.','Lamp development alone does not establish local electricity supply.','menlo','nps_edison')
add('US_EDISON_DEMO','lighting','US',1879,12,'31 December: public demonstration of Edison incandescent lighting system at Menlo Park.','Demonstration/publicity must be separated from diffusion.','nps_edison','si_light')
add('UK_GODALMING','lighting','UK',1881,9,'26 September: Godalming electric lighting experiment; public supply scheme serves streets and private customers. NOT the first electric street lighting anywhere; broad local first-town claims conflict with museum qualification.','A small local supply cannot stand for national electrification or the end of darkness obstacles.','godalming','iet_power','high for year/local scheme; priority claims require qualification')
add('US_PEARL_STREET','lighting','US',1882,9,'4 September: Edison Pearl Street central station begins supplying customers in lower Manhattan.','Electric light initially has sharply bounded local availability.','nps_timeline','si_pearl')
columns=['event_id','domain','country','year','month','event','significance_for_fiction','source1_url','source1_title','source2_url','source2_title','confidence']
with Path('research/history/timeline.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.writer(f);w.writerow(columns);w.writerows(sorted(rows,key=lambda r:(r[3],int(r[4] or 0),r[0])))
print(f'Wrote {len(rows)} rows')
