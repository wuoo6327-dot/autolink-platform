import assert from 'node:assert/strict';
import {filterReferenceModels, reviewedAliases, energyTokens} from '../site/trade/model-directory.mjs';

const models=[
  {id:'geely-monjaro-2026',brand:'Geely',model:'Monjaro',year:2026,energy:'ICE, HEV',bodyType:'SUV'},
  {id:'byd-song-2025',brand:'BYD',model:'Song Plus',year:2025,energy:'PHEV',bodyType:'SUV'},
];
const aliases=reviewedAliases({
  'geely-monjaro-2026':{status:'approved',modelName:'Monjaro / Xingyue L'},
  'byd-song-2025':{status:'pending',modelName:'Unreviewed Alias'},
});
assert.deepEqual(filterReferenceModels(models,{keyword:'xingyue',brand:'Geely',year:'2026',energy:'ICE'},aliases).map(x=>x.id),['geely-monjaro-2026']);
assert.deepEqual(filterReferenceModels(models,{keyword:'unreviewed'},aliases),[]);
assert.deepEqual(filterReferenceModels(models,{brand:'BYD',year:'2026'},aliases),[]);
assert.deepEqual(filterReferenceModels(models,{energy:'PHEV',bodyType:'SUV'},aliases).map(x=>x.id),['byd-song-2025']);
assert.deepEqual(energyTokens('ICE, HEV'),['ICE','HEV']);
assert.deepEqual(filterReferenceModels(models,{energy:'HEV'},aliases).map(x=>x.id),['geely-monjaro-2026']);
