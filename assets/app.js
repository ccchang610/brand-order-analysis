const T={all:"\u5168\u53f0",north:"\u5317\u90e8",central:"\u4e2d\u90e8",south:"\u5357\u90e8",east:"\u6771\u90e8",islands:"\u96e2\u5cf6",allCities:"\u5168\u90e8\u57ce\u5e02",allSystems:"\u5168\u90e8\u7cfb\u7d71",updated:"\u66f4\u65b0",noData:"\u6c92\u6709\u53ef\u89e3\u6790\u8cc7\u6599",officialStores:"\u5b98\u65b9\u9580\u5e02",currentFilter:"\u76ee\u524d\u7be9\u9078\u7bc4\u570d",gmbMapsFound:"GMB/Maps \u627e\u5230",googleFound:"Google \u627e\u5230",thirdParty:"\u7b2c\u4e09\u65b9\u4f86\u6e90",gmbGap:"Google Order \u4f9b\u61c9\u5546\u7f3a\u53e3",gmbNotFound:"GMB/Maps \u672a\u627e\u5230",mapGap:"\u5b98\u65b9\u6709\u9580\u5e02\u4f46\u672a\u627e\u5230 GMB",notNoAdoption:"\u4e0d\u7b49\u65bc\u672a\u5c0e\u5165",anySystem:"\u6709\u4efb\u4e00\u7cfb\u7d71",pickupStores:"\u81ea\u53d6\u9580\u5e02",deliveryStores:"\u5916\u9001\u9580\u5e02",unknownStores:"\u672a\u77e5\u9580\u5e02",noEvidence:"\u672a\u898b\u5b98\u65b9/\u5e73\u53f0/Google Order \u4f9b\u61c9\u5546\u8b49\u64da",mainSystems:"\u4e3b\u8981\u7cfb\u7d71\u6578",allSources:"\u5168\u4f86\u6e90",gmbHasSystem:"Google Order \u6709\u4f9b\u61c9\u5546",gmbPickup:"Google Order \u81ea\u53d6\u4f9b\u61c9\u5546",gmbDelivery:"Google Order \u5916\u9001\u4f9b\u61c9\u5546",gmbPanel:"Google Order \u9762\u677f",noPanel:"\u672a\u78ba\u8a8d Google Order \u4f9b\u61c9\u5546\u6216 Google \u963b\u64cb",gmbFoundStores:"GMB \u627e\u5230\u9580\u5e02",noLink:"\u672a\u898b\u9023\u7d50",pickup:"\u81ea\u53d6",delivery:"\u5916\u9001",unknown:"\u672a\u77e5",stores:"\u5bb6\u9580\u5e02"};
const regions=[T.all,T.north,T.central,T.south,T.east,T.islands];
let stores=[],summary={};
const state={region:T.all,city:"all",system:"all",gmb:"all",q:""};
const mapCountPositions={"\u57fa\u9686\u5e02":[69.2,39.4],"\u53f0\u5317\u5e02":[60.0,42.1],"\u65b0\u5317\u5e02":[66.4,47.4],"\u6843\u5712\u5e02":[55.0,44.5],"\u65b0\u7af9\u5e02":[48.8,47.8],"\u65b0\u7af9\u7e23":[55.4,52.4],"\u82d7\u6817\u7e23":[50.0,55.6],"\u53f0\u4e2d\u5e02":[52.4,59.1],"\u5f70\u5316\u7e23":[40.2,62.7],"\u5357\u6295\u7e23":[55.3,65.4],"\u96f2\u6797\u7e23":[39.5,67.8],"\u5609\u7fa9\u7e23":[45.6,73.2],"\u5609\u7fa9\u5e02":[40.5,71.1],"\u53f0\u5357\u5e02":[39.4,77.0],"\u9ad8\u96c4\u5e02":[45.0,83.3],"\u5c4f\u6771\u7e23":[48.8,91.2],"\u5b9c\u862d\u7e23":[65.2,53.3],"\u82b1\u84ee\u7e23":[60.8,67.8],"\u53f0\u6771\u7e23":[55.2,82.3]};
const byId=id=>document.getElementById(id);
const pct=value=>`${Math.round((value||0)*1000)/10}%`;

loadData().then(([storePayload,summaryPayload])=>{stores=storePayload.stores;summary=summaryPayload;init();render();}).catch(error=>{byId("generatedAt").textContent="Data load failed";console.error(error);});

async function loadData(){if(window.DAMING_DATA)return[window.DAMING_DATA.storesPayload,window.DAMING_DATA.summary];return Promise.all([fetch("data/stores.json").then(r=>r.json()),fetch("data/summary.json").then(r=>r.json())]);}
function init(){const updatedAt=summary.generatedAt||summary.checkedAt||stores[0]?.checkedAt||"";byId("generatedAt").textContent=`${T.updated} ${updatedAt}`;byId("regionFilters").innerHTML=regions.map(region=>`<button data-region="${region}">${region}</button>`).join("");byId("regionFilters").addEventListener("click",event=>{if(!event.target.dataset.region)return;state.region=event.target.dataset.region;state.city="all";render();});byId("cityFilter").addEventListener("change",event=>{state.city=event.target.value;render();});byId("systemFilter").addEventListener("change",event=>{state.system=event.target.value;render();});byId("gmbFilter").addEventListener("change",event=>{state.gmb=event.target.value;render();});byId("searchInput").addEventListener("input",event=>{state.q=event.target.value.trim().toLowerCase();render();});}
function filteredRows(){return stores.filter(store=>{if(state.region!==T.all&&store.regionGroup!==state.region)return false;if(state.city!=="all"&&store.city!==state.city)return false;if(state.system!=="all"&&!storeHasSystem(store,state.system))return false;if(state.gmb==="confirmed"&&!storeHasGmbProvider(store))return false;if(state.gmb==="gap"&&storeHasGoogleOrderEntry(store))return false;if(state.gmb==="no_gmb_found"&&store.sourceCoverage.gmbFound)return false;if(state.q&&!`${store.storeName} ${store.address} ${store.city} ${store.district}`.toLowerCase().includes(state.q))return false;return true;});}
function render(){document.querySelectorAll("#regionFilters button").forEach(button=>button.classList.toggle("active",button.dataset.region===state.region));const cities=[...new Set(stores.filter(store=>state.region===T.all||store.regionGroup===state.region).map(store=>store.city).filter(Boolean))].sort();byId("cityFilter").innerHTML=`<option value="all">${T.allCities}</option>${cities.map(city=>`<option ${state.city===city?"selected":""}>${city}</option>`).join("")}`;const systems=[...new Set(stores.flatMap(store=>[...store.orderingSystems.map(claim=>claim.system),...(store.gmbOrderLinks||[]).map(link=>link.platform)]).filter(Boolean))].sort();byId("systemFilter").innerHTML=`<option value="all">${T.allSystems}</option>${systems.map(system=>`<option ${state.system===system?"selected":""}>${system}</option>`).join("")}`;const rows=filteredRows();renderInsights(rows);renderKpis(rows);renderMap(rows);renderStoreDistribution(rows);renderModeCharts(rows);renderGmbCharts(rows);renderComparison(rows);renderDetails(rows);}
function countSystems(rows,options={}){const counts=new Map();rows.forEach(store=>{const systems=new Set();store.orderingSystems.forEach(claim=>{if(options.sourceType&&claim.sourceType!==options.sourceType)return;if(options.mode&&!claim.orderMode.includes(options.mode))return;systems.add(claim.system);});systems.forEach(system=>counts.set(system,(counts.get(system)||0)+1));});return[...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));}
function googleOrderOptionPlatforms(store,mode){const systems=new Set();store.orderingSystems.forEach(claim=>{if(claim.sourceType!=="gmb")return;if(mode&&!claim.orderMode.includes(mode))return;systems.add(claim.system);});(store.gmbOrderLinks||[]).forEach(link=>{if(mode&&!(link.orderMode||[]).includes(mode))return;systems.add(link.platform);});return systems;}
function countGoogleOrderOptions(rows,options={}){const counts=new Map();rows.forEach(store=>{googleOrderOptionPlatforms(store,options.mode).forEach(system=>{if(system)counts.set(system,(counts.get(system)||0)+1);});});return[...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));}
function storeHasSystem(store,system){return store.orderingSystems.some(claim=>claim.system===system)||(store.gmbOrderLinks||[]).some(link=>link.platform===system);}
function storeHasGmbProvider(store){return store.orderingSystems.some(claim=>claim.sourceType==="gmb"&&claim.system);}
function storeHasGoogleOrderEntry(store){return !!store.hasGmbOrderingSystem||store.gmbOrderingStatus==="confirmed"||store.gmbOrderingStatus==="button_confirmed_provider_pending";}
function renderKpis(rows){const total=rows.length||0;const gmbFound=rows.filter(store=>store.sourceCoverage.gmbFound).length;const gmbMissing=rows.filter(store=>!store.sourceCoverage.gmbFound).length;const googleFound=rows.filter(store=>store.sourceCoverage.googleFound).length;const thirdPartyFound=rows.filter(store=>store.sourceCoverage.thirdPartyFound).length;const anyOrdering=rows.filter(store=>store.hasAnyOrderingSystem).length;const gmbOrdering=rows.filter(store=>storeHasGmbProvider(store)).length;const gmbGap=rows.filter(store=>!storeHasGoogleOrderEntry(store)).length;const allPickupStores=rows.filter(store=>store.orderingSystems.some(claim=>claim.orderMode.includes("pickup"))).length;const allDeliveryStores=rows.filter(store=>store.orderingSystems.some(claim=>claim.orderMode.includes("delivery"))).length;const gmbPickupStores=rows.filter(store=>googleOrderOptionPlatforms(store,"pickup").size).length;const gmbDeliveryStores=rows.filter(store=>googleOrderOptionPlatforms(store,"delivery").size).length;byId("storeKpis").innerHTML=kpis([[T.officialStores,total,T.currentFilter],[T.gmbMapsFound,gmbFound,total?pct(gmbFound/total):"0%"],[T.gmbNotFound,gmbMissing,T.mapGap],[T.googleFound,googleFound,total?pct(googleFound/total):"0%"],[T.thirdParty,thirdPartyFound,total?pct(thirdPartyFound/total):"0%"],[T.gmbGap,gmbGap,T.notNoAdoption]]);byId("allSourceKpis").innerHTML=kpis([[T.anySystem,anyOrdering,total?pct(anyOrdering/total):"0%"],[T.pickupStores,allPickupStores,T.allSources],[T.deliveryStores,allDeliveryStores,T.allSources],[T.unknownStores,total-anyOrdering,T.noEvidence],[T.mainSystems,countSystems(rows).length,T.allSources]]);byId("gmbKpis").innerHTML=kpis([[T.gmbHasSystem,gmbOrdering,total?pct(gmbOrdering/total):"0%"],[T.gmbPickup,gmbPickupStores,T.gmbPanel],[T.gmbDelivery,gmbDeliveryStores,T.gmbPanel],[T.gmbGap,gmbGap,T.noPanel],[T.gmbNotFound,gmbMissing,T.mapGap],[T.gmbFoundStores,gmbFound,total?pct(gmbFound/total):"0%"]]);}
function kpis(items){return items.map(([label,value,note])=>`<div class="kpi"><strong>${value}</strong><span>${systemKey(label)==="other"?label:systemBadge(label)}</span><span>${note}</span></div>`).join("");}
function renderInsights(rows){const total=rows.length||0;const gmbOrdering=rows.filter(store=>storeHasGmbProvider(store)).length;const gmbGap=rows.filter(store=>!storeHasGoogleOrderEntry(store)).length;const anyOrdering=rows.filter(store=>store.hasAnyOrderingSystem).length;const topCity=[...rows.reduce((map,store)=>map.set(store.city,(map.get(store.city)||0)+1),new Map()).entries()].sort((a,b)=>b[1]-a[1])[0]||["-",0];const gmbDelivery=countGoogleOrderOptions(rows,{mode:"delivery"});const leadingDelivery=gmbDelivery[0]||["-",0];byId("insightStrip").innerHTML=`<article><span>\u9580\u5e02\u898f\u6a21</span><strong>${total}</strong><p>${topCity[0]} ${topCity[1]} \u5bb6\u6700\u96c6\u4e2d</p></article><article><span>\u5168\u4f86\u6e90\u5c0e\u5165</span><strong>${total?pct(anyOrdering/total):"0%"}</strong><p>${anyOrdering}/${total} \u5bb6\u6709\u4efb\u4e00\u9ede\u9910\u8b49\u64da</p></article><article><span>Google Order \u4f9b\u61c9\u5546\u8986\u84cb</span><strong>${total?pct(gmbOrdering/total):"0%"}</strong><p>${gmbOrdering} \u5bb6\u6709 Google Order \u4f9b\u61c9\u5546\u8b49\u64da</p></article><article class="warn"><span>Google Order \u4f9b\u61c9\u5546\u7f3a\u53e3</span><strong>${gmbGap}</strong><p>\u672a\u78ba\u8a8d Google Order \u4f9b\u61c9\u5546\u8b49\u64da</p></article><article><span>Google Order \u4e3b\u8981\u4f9b\u61c9\u5546/\u9023\u7d50</span><strong>${systemBadge(leadingDelivery[0])}</strong><p>${leadingDelivery[1]} \u5bb6\u9580\u5e02</p></article>`;}
function renderMap(rows){const mapRows=stores.filter(store=>{if(state.region!==T.all&&store.regionGroup!==state.region)return false;if(state.system!=="all"&&!storeHasSystem(store,state.system))return false;if(state.gmb==="confirmed"&&!storeHasGmbProvider(store))return false;if(state.gmb==="gap"&&storeHasGoogleOrderEntry(store))return false;if(state.gmb==="no_gmb_found"&&store.sourceCoverage.gmbFound)return false;if(state.q&&!`${store.storeName} ${store.address} ${store.city} ${store.district}`.toLowerCase().includes(state.q))return false;return true;});const counts=new Map();mapRows.forEach(store=>counts.set(store.city,(counts.get(store.city)||0)+1));const map=window.TAIWAN_MAP;if(!map){byId("taiwanMap").innerHTML=`<p class="muted">${T.noData}</p>`;return;}const normalizeCity=city=>city.replace("\u81fa","\u53f0");const islandSet=new Set(["\u9023\u6c5f\u7e23","\u91d1\u9580\u7e23","\u6f8e\u6e56\u7e23"]);const countFor=city=>counts.get(city)||counts.get(normalizeCity(city))||0;const max=Math.max(1,...map.shapes.map(shape=>countFor(shape.name)));const mainShapes=map.shapes.filter(shape=>!islandSet.has(shape.name));const islandShapes=map.shapes.filter(shape=>islandSet.has(shape.name));const countyNode=shape=>{const city=shape.name;const displayCity=normalizeCity(city);const count=countFor(city);const intensity=count/max;const isSelected=state.city!=="all";const active=state.city===city||state.city===displayCity?" active":"";const dim=isSelected&&!active?" dimmed":"";const hasCount=count>0?" has-count":"";const top=!isSelected&&count>0&&count===max?" top-count":"";return`<g class="county-node${active}${dim}${hasCount}${top}" data-city="${displayCity}" tabindex="0" role="button" aria-label="${displayCity} ${count}"><path d="${shape.d}" style="--i:${intensity.toFixed(3)}"></path><g class="map-label" transform="translate(${shape.labelX} ${shape.labelY})"><text class="map-city" y="-3">${displayCity}</text><text class="map-count" y="4">${count}</text></g></g>`;};const mainCounties=mainShapes.map(countyNode).join("");const islands=islandShapes.map(shape=>{const displayCity=normalizeCity(shape.name);const count=countFor(shape.name);const active=state.city===displayCity?" active":"";const dim=state.city!=="all"&&!active?" dimmed":"";return`<button class="island-chip${active}${dim}" data-city="${displayCity}" type="button"><span>${displayCity}</span><strong>${count}</strong></button>`;}).join("");byId("taiwanMap").innerHTML=`<svg class="map-outline" viewBox="22 34 60 72" role="img" aria-label="Taiwan county store distribution">${mainCounties}</svg><div class="island-strip">${islands}</div>`;byId("taiwanMap").querySelectorAll(".county-node,.island-chip").forEach(node=>{node.addEventListener("click",()=>{state.city=node.dataset.city;render();});node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){state.city=node.dataset.city;render();}});});}
function renderMap(rows){
  const mapRows=stores.filter(store=>{
    if(state.region!==T.all&&store.regionGroup!==state.region)return false;
    if(state.system!=="all"&&!storeHasSystem(store,state.system))return false;
    if(state.gmb==="confirmed"&&!storeHasGmbProvider(store))return false;
    if(state.gmb==="gap"&&storeHasGoogleOrderEntry(store))return false;
    if(state.gmb==="no_gmb_found"&&store.sourceCoverage.gmbFound)return false;
    if(state.q&&!`${store.storeName} ${store.address} ${store.city} ${store.district}`.toLowerCase().includes(state.q))return false;
    return true;
  });
  const counts=new Map();
  mapRows.forEach(store=>counts.set(store.city,(counts.get(store.city)||0)+1));
  const map=window.TAIWAN_MAP;
  if(!map){byId("taiwanMap").innerHTML=`<p class="muted">${T.noData}</p>`;return;}
  const normalizeCity=city=>city.replace("\u81fa","\u53f0");
  const islandSet=new Set(["\u9023\u6c5f\u7e23","\u91d1\u9580\u7e23","\u6f8e\u6e56\u7e23"]);
  const countFor=city=>counts.get(city)||counts.get(normalizeCity(city))||0;
  const max=Math.max(1,...map.shapes.map(shape=>countFor(shape.name)));
  const mainShapes=map.shapes.filter(shape=>!islandSet.has(shape.name));
  const islandShapes=map.shapes.filter(shape=>islandSet.has(shape.name));
  const countyNode=shape=>{
    const city=shape.name;
    const displayCity=normalizeCity(city);
    const count=countFor(city);
    const intensity=count/max;
    const isSelected=state.city!=="all";
    const active=state.city===city||state.city===displayCity?" active":"";
    const dim=isSelected&&!active?" dimmed":"";
    const hasCount=count>0?" has-count":"";
    const noCount=count===0?" no-count":"";
    const top=!isSelected&&count>0&&count===max?" top-count":"";
    const point=mapLabelOverrides[displayCity]||[shape.labelX,shape.labelY];
    const label=count>0||active
      ? `<text class="map-city" y="-4.7">${displayCity}</text><text class="map-count" y="3.9">${count}</text>`
      : `<text class="map-city zero-city" y="0">${displayCity}</text>`;
    return `<g class="county-node${active}${dim}${hasCount}${noCount}${top}" data-city="${displayCity}" tabindex="0" role="button" aria-label="${displayCity} ${count}"><path d="${shape.d}" style="--i:${intensity.toFixed(3)}"></path><g class="map-label" transform="translate(${point[0]} ${point[1]})">${label}</g></g>`;
  };
  const mainCounties=mainShapes.map(countyNode).join("");
  const islands=islandShapes.map(shape=>{
    const displayCity=normalizeCity(shape.name);
    const count=countFor(shape.name);
    const active=state.city===displayCity?" active":"";
    const dim=state.city!=="all"&&!active?" dimmed":"";
    return `<button class="island-chip${active}${dim}" data-city="${displayCity}" type="button"><span>${displayCity}</span><strong>${count}</strong></button>`;
  }).join("");
  byId("taiwanMap").innerHTML=`<svg class="map-outline" viewBox="22 34 60 72" role="img" aria-label="Taiwan county store distribution">${mainCounties}</svg><div class="island-strip">${islands}</div>`;
  byId("taiwanMap").querySelectorAll(".county-node,.island-chip").forEach(node=>{
    node.addEventListener("click",()=>{state.city=node.dataset.city;render();});
    node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){state.city=node.dataset.city;render();}});
  });
}
function renderMap(rows){
  const mapRows=stores.filter(store=>{
    if(state.region!==T.all&&store.regionGroup!==state.region)return false;
    if(state.system!=="all"&&!storeHasSystem(store,state.system))return false;
    if(state.gmb==="confirmed"&&!storeHasGmbProvider(store))return false;
    if(state.gmb==="gap"&&storeHasGoogleOrderEntry(store))return false;
    if(state.gmb==="no_gmb_found"&&store.sourceCoverage.gmbFound)return false;
    if(state.q&&!`${store.storeName} ${store.address} ${store.city} ${store.district}`.toLowerCase().includes(state.q))return false;
    return true;
  });
  const counts=new Map();
  mapRows.forEach(store=>counts.set(store.city,(counts.get(store.city)||0)+1));
  const map=window.TAIWAN_MAP;
  if(!map){byId("taiwanMap").innerHTML=`<p class="muted">${T.noData}</p>`;return;}
  const normalizeCity=city=>city.replace("\u81fa","\u53f0");
  const islandSet=new Set(["\u9023\u6c5f\u7e23","\u91d1\u9580\u7e23","\u6f8e\u6e56\u7e23"]);
  const countFor=city=>counts.get(city)||counts.get(normalizeCity(city))||0;
  const max=Math.max(1,...map.shapes.map(shape=>countFor(shape.name)));
  const mainShapes=map.shapes.filter(shape=>!islandSet.has(shape.name));
  const islandShapes=map.shapes.filter(shape=>islandSet.has(shape.name));
  const metaFor=shape=>{
    const city=shape.name;
    const displayCity=normalizeCity(city);
    const count=countFor(city);
    const isSelected=state.city!=="all";
    const active=state.city===city||state.city===displayCity?" active":"";
    const dim=isSelected&&!active?" dimmed":"";
    const hasCount=count>0?" has-count":"";
    const noCount=count===0?" no-count":"";
    const top=!isSelected&&count>0&&count===max?" top-count":"";
    const point=mapLabelOverrides[displayCity]||[shape.labelX,shape.labelY];
    const className=`${active}${dim}${hasCount}${noCount}${top}`;
    return{city,displayCity,count,intensity:count/max,point,className};
  };
  const countyPath=shape=>{
    const meta=metaFor(shape);
    return`<g class="county-node${meta.className}" data-city="${meta.displayCity}" tabindex="0" role="button" aria-label="${meta.displayCity} ${meta.count}"><path d="${shape.d}" style="--i:${meta.intensity.toFixed(3)}"></path></g>`;
  };
  const countyLabel=shape=>{
    const meta=metaFor(shape);
    const label=meta.count>0||meta.className.includes("active")
      ? `<text class="map-city" y="-4.7">${meta.displayCity}</text><text class="map-count" y="3.9">${meta.count}</text>`
      : `<text class="map-city zero-city" y="0">${meta.displayCity}</text>`;
    return`<g class="map-label-node${meta.className}" data-city="${meta.displayCity}"><g class="map-label" transform="translate(${meta.point[0]} ${meta.point[1]})">${label}</g></g>`;
  };
  const mainPaths=mainShapes.map(countyPath).join("");
  const mainLabels=mainShapes.map(countyLabel).join("");
  const islands=islandShapes.map(shape=>{
    const displayCity=normalizeCity(shape.name);
    const count=countFor(shape.name);
    const active=state.city===displayCity?" active":"";
    const dim=state.city!=="all"&&!active?" dimmed":"";
    return `<button class="island-chip${active}${dim}" data-city="${displayCity}" type="button"><span>${displayCity}</span><strong>${count}</strong></button>`;
  }).join("");
  byId("taiwanMap").innerHTML=`<svg class="map-outline" viewBox="22 34 60 72" role="img" aria-label="Taiwan county store distribution"><g class="map-shape-layer">${mainPaths}</g><g class="map-label-layer">${mainLabels}</g></svg><div class="island-strip">${islands}</div>`;
  byId("taiwanMap").querySelectorAll(".county-node,.island-chip").forEach(node=>{
    node.addEventListener("click",()=>{state.city=node.dataset.city;render();});
    node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){state.city=node.dataset.city;render();}});
  });
}
function renderMap(rows){
  const mapRows=stores.filter(store=>{
    if(state.region!==T.all&&store.regionGroup!==state.region)return false;
    if(state.system!=="all"&&!storeHasSystem(store,state.system))return false;
    if(state.gmb==="confirmed"&&!storeHasGmbProvider(store))return false;
    if(state.gmb==="gap"&&storeHasGoogleOrderEntry(store))return false;
    if(state.gmb==="no_gmb_found"&&store.sourceCoverage.gmbFound)return false;
    if(state.q&&!`${store.storeName} ${store.address} ${store.city} ${store.district}`.toLowerCase().includes(state.q))return false;
    return true;
  });
  const counts=new Map();
  mapRows.forEach(store=>counts.set(store.city,(counts.get(store.city)||0)+1));
  const map=window.TAIWAN_MAP;
  if(!map){byId("taiwanMap").innerHTML=`<p class="muted">${T.noData}</p>`;return;}
  const normalizeCity=city=>city.replace("\u81fa","\u53f0");
  const islandSet=new Set(["\u9023\u6c5f\u7e23","\u91d1\u9580\u7e23","\u6f8e\u6e56\u7e23"]);
  const countFor=city=>counts.get(city)||counts.get(normalizeCity(city))||0;
  const max=Math.max(1,...map.shapes.map(shape=>countFor(shape.name)));
  const mainShapes=map.shapes.filter(shape=>!islandSet.has(shape.name));
  const islandShapes=map.shapes.filter(shape=>islandSet.has(shape.name));
  const metaFor=shape=>{
    const city=shape.name;
    const displayCity=normalizeCity(city);
    const count=countFor(city);
    const isSelected=state.city!=="all";
    const active=state.city===city||state.city===displayCity?" active":"";
    const dim=isSelected&&!active?" dimmed":"";
    const hasCount=count>0?" has-count":"";
    const noCount=count===0?" no-count":"";
    const top=!isSelected&&count>0&&count===max?" top-count":"";
    const point=mapCountPositions[displayCity]||[shape.labelX,shape.labelY];
    return{city,displayCity,count,intensity:count/max,point,className:`${active}${dim}${hasCount}${noCount}${top}`};
  };
  const countyPath=shape=>{
    const meta=metaFor(shape);
    return`<g class="county-node${meta.className}" data-city="${meta.displayCity}" tabindex="0" role="button" aria-label="${meta.displayCity} ${meta.count} \u5bb6\u9580\u5e02"><title>${meta.displayCity} ${meta.count} \u5bb6\u9580\u5e02</title><path d="${shape.d}" style="--i:${meta.intensity.toFixed(3)}"></path></g>`;
  };
  const countyMarker=shape=>{
    const meta=metaFor(shape);
    if(meta.count===0&&!meta.className.includes("active"))return"";
    return`<g class="map-marker-node${meta.className}" data-city="${meta.displayCity}" transform="translate(${meta.point[0]} ${meta.point[1]})"><circle r="2.18"></circle><text y=".72">${meta.count}</text></g>`;
  };
  const mainPaths=mainShapes.map(countyPath).join("");
  const mainMarkers=mainShapes.map(countyMarker).join("");
  const rankedCities=[...counts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,22);
  const cityChips=rankedCities.map(([city,count])=>`<button class="city-chip${state.city===city?" active":""}" data-city="${city}" type="button"><span>${city}</span><strong>${count}</strong></button>`).join("");
  const islands=islandShapes.map(shape=>{
    const displayCity=normalizeCity(shape.name);
    const count=countFor(shape.name);
    const active=state.city===displayCity?" active":"";
    const dim=state.city!=="all"&&!active?" dimmed":"";
    return `<button class="island-chip${active}${dim}" data-city="${displayCity}" type="button"><span>${displayCity}</span><strong>${count}</strong></button>`;
  }).join("");
  byId("taiwanMap").innerHTML=`<svg class="map-outline" viewBox="22 34 60 72" role="img" aria-label="Taiwan county store distribution"><g class="map-shape-layer">${mainPaths}</g><g class="map-marker-layer">${mainMarkers}</g></svg><div class="map-tooltip" aria-hidden="true"></div><div class="map-chip-panel">${cityChips}</div><div class="island-strip">${islands}</div>`;
  const tooltip=byId("taiwanMap").querySelector(".map-tooltip");
  byId("taiwanMap").querySelectorAll(".county-node").forEach(node=>{
    node.addEventListener("click",()=>{state.city=node.dataset.city;render();});
    node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){state.city=node.dataset.city;render();}});
    node.addEventListener("pointerenter",event=>{tooltip.textContent=node.getAttribute("aria-label");tooltip.classList.add("visible");});
    node.addEventListener("pointermove",event=>{const rect=byId("taiwanMap").getBoundingClientRect();tooltip.style.left=`${event.clientX-rect.left+12}px`;tooltip.style.top=`${event.clientY-rect.top+12}px`;});
    node.addEventListener("pointerleave",()=>tooltip.classList.remove("visible"));
  });
  byId("taiwanMap").querySelectorAll(".city-chip,.island-chip").forEach(node=>{
    node.addEventListener("click",()=>{state.city=node.dataset.city;render();});
    node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){state.city=node.dataset.city;render();}});
  });
}
function regionOf(city){return stores.find(store=>store.city===city)?.regionGroup||T.islands;}
function renderStoreDistribution(rows){const cityCounts=[...rows.reduce((map,store)=>map.set(store.city,(map.get(store.city)||0)+1),new Map()).entries()].sort((a,b)=>b[1]-a[1]).slice(0,12);byId("cityBars").innerHTML=bars(cityCounts,"");}
function renderModeCharts(rows){byId("pickupBars").innerHTML=bars(countSystems(rows,{mode:"pickup"}),"",true);byId("deliveryBars").innerHTML=bars(countSystems(rows,{mode:"delivery"}),"alt",true);const regionRows=regions.filter(region=>region!==T.all).map(region=>{const scoped=rows.filter(store=>store.regionGroup===region);const adopted=scoped.filter(store=>store.hasAnyOrderingSystem).length;return[region,scoped.length?adopted/scoped.length:0,`${adopted}/${scoped.length}`];});byId("regionMatrix").innerHTML=regionRows.map(([region,rate,label])=>`<div class="matrix-row"><span>${region}</span><div class="matrix-track"><div class="matrix-fill" style="width:${rate*100}%"></div></div><b>${label}</b></div>`).join("");}
function renderGmbCharts(rows){byId("gmbPickupBars").innerHTML=bars(countGoogleOrderOptions(rows,{mode:"pickup"}),"",true);byId("gmbDeliveryBars").innerHTML=bars(countGoogleOrderOptions(rows,{mode:"delivery"}),"alt",true);}
function systemKey(system){const value=(system||"").toLowerCase().replace(/\s+/g,"");if(value==="nidin"||value.includes("nidin"))return"nidin";if(value==="ubereats"||value.includes("ubereats"))return"uber-eats";if(value==="foodpanda"||value.includes("foodpanda"))return"foodpanda";if(value==="line"||value.includes("line"))return"line";if(value==="instagram"||value.includes("instagram"))return"instagram";if(value==="quickclick"||value.includes("quickclick")||value.includes("快一點"))return"quickclick";return"other";}
function systemLogo(system){return`<span class="platform-logo platform-${systemKey(system)}">${system}</span>`;}
function systemBadge(system){return`<span class="platform-chip platform-${systemKey(system)}">${system}</span>`;}
function systemList(systems){return[...systems].map(systemBadge).join("");}
function bars(entries,className,usePlatform=false){const max=Math.max(1,...entries.map(entry=>entry[1]));if(!entries.length)return`<p class="muted">${T.noData}</p>`;return entries.map(([name,value])=>{const rowClass=usePlatform?` platform-row platform-brand-${systemKey(name)}`:"";const label=usePlatform?systemLogo(name):name;return`<div class="bar-row${rowClass}"><span>${label}</span><div class="bar-track"><div class="bar-fill ${className}" style="width:${value/max*100}%"></div></div><b>${value}</b></div>`;}).join("");}
function renderComparison(rows){const allCounts=countSystems(rows);const gmbCounts=new Map(countSystems(rows,{sourceType:"gmb"}));const total=rows.length||1;byId("comparisonRows").innerHTML=allCounts.map(([system,count])=>{const gmbCount=gmbCounts.get(system)||0;return`<tr><td>${systemBadge(system)}</td><td>${count}</td><td>${pct(count/total)}</td><td>${gmbCount}</td><td>${pct(gmbCount/total)}</td><td>${count-gmbCount}</td></tr>`;}).join("")||`<tr><td colspan="6">${T.noData}</td></tr>`;}
function renderDetails(rows){
  byId("detailCount").textContent=`${rows.length} ${T.stores}`;
  byId("storeRows").innerHTML=rows.map(store=>{
    const allSummary=modeSummary(store.orderingSystems);
    const gmbSummary=googleOrderSummary(store);
    const gmbStatusLabel=store.gmbOrderingStatus==="button_confirmed_provider_pending"?"Google Order 有點餐入口，供應商待解析":store.gmbOrderingStatus==="unavailable_or_blocked"?"Google 阻擋/逾時，需人工複核":store.gmbOrderingStatus==="no_gmb_order_button"?"未找到 Google Order 藍色入口":store.gmbOrderingStatus;
    const links=store.orderingSystems.filter(claim=>claim.evidenceUrl).slice(0,5).map(claim=>`<a href="${claim.evidenceUrl}" target="_blank">${claim.label||claim.system}</a>`).join("、");
    const orderLinks=(store.gmbOrderLinks||[]).slice(0,8).map(link=>{const modes=(link.orderMode||[]).map(mode=>mode==="pickup"?T.pickup:mode==="delivery"?T.delivery:mode).join("/");return link.href?`<a href="${link.href}" target="_blank">${systemBadge(link.platform)}<small>${modes}</small></a>`:`<span>${systemBadge(link.platform)}<small>${modes}</small></span>`;}).join("");
    const orderLinkBlock=orderLinks?`<div class="order-link-list"><b>&#40670;&#39184;&#36899;&#32080;</b>${orderLinks}</div>`:"";
    const gmbLink=store.gmbUrl?`<a href="${store.gmbUrl}" target="_blank">GMB/Maps</a>`:`<span class="pill gap">${T.gmbNotFound}</span>`;
    const signal=store.gmbSignals||{};
    const panelUrl=store.gmbOrderPanelUrl||signal.panelUrl||"";
    const panelLink=panelUrl&&panelUrl!==store.gmbUrl?`<a href="${panelUrl}" target="_blank">Google Order 入口</a>`:"";
    const signalLabel=signal.buttonDetected&&!signal.providersParsed&&store.gmbOrderingStatus!=="button_confirmed_provider_pending"?`<span class="pill gap">已確認藍色按鈕</span>`:"";
    const reviewNote=store.manualReviewReason?`<small class="review-note">${store.manualReviewReason}</small>`:"";
    const evidence=[gmbLink,panelLink,links,orderLinkBlock].filter(Boolean).join("、");
    return`<tr><td><b>${store.storeName}</b><br><small>${store.phone||""}</small></td><td>${store.regionGroup}<br>${store.city} ${store.district}</td><td>${store.address}</td><td>${allSummary||`<span class="pill gap">${T.noLink}</span>`}</td><td>${gmbSummary||`<span class="pill gap">${gmbStatusLabel}</span>`}${signalLabel}</td><td>${evidence}${reviewNote}</td></tr>`;
  }).join("");
}
function googleOrderSummary(store){
  const groups={pickup:new Set(),delivery:new Set(),unknown:new Set()};
  store.orderingSystems.filter(claim=>claim.sourceType==="gmb").forEach(claim=>{
    const modes=claim.orderMode.length?claim.orderMode:["unknown"];
    modes.forEach(mode=>(groups[mode]||groups.unknown).add(claim.system));
  });
  (store.gmbOrderLinks||[]).forEach(link=>{
    const modes=(link.orderMode||[]).length?link.orderMode:["unknown"];
    modes.forEach(mode=>(groups[mode]||groups.unknown).add(link.platform));
  });
  const labels=[];
  if(groups.pickup.size)labels.push(`<span class="mode-pill">${T.pickup}\uff1a${systemList(groups.pickup)}</span>`);
  if(groups.delivery.size)labels.push(`<span class="mode-pill">${T.delivery}\uff1a${systemList(groups.delivery)}</span>`);
  if(groups.unknown.size)labels.push(`<span class="mode-pill gap">${T.unknown}\uff1a${systemList(groups.unknown)}</span>`);
  return labels.join("");
}
function modeSummary(claims){const groups={pickup:new Set(),delivery:new Set(),unknown:new Set()};claims.forEach(claim=>{const modes=claim.orderMode.length?claim.orderMode:["unknown"];modes.forEach(mode=>(groups[mode]||groups.unknown).add(claim.system));});const labels=[];if(groups.pickup.size)labels.push(`<span class="mode-pill">${T.pickup}\uff1a${systemList(groups.pickup)}</span>`);if(groups.delivery.size)labels.push(`<span class="mode-pill">${T.delivery}\uff1a${systemList(groups.delivery)}</span>`);if(groups.unknown.size)labels.push(`<span class="mode-pill gap">${T.unknown}\uff1a${systemList(groups.unknown)}</span>`);return labels.join("");}


