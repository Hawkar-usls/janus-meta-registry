"use strict";
// Run offline: node --test nexus/receipt_integrity.test.cjs
const { test } = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");

const APP = fs.readFileSync("nexus/app.js", "utf8");
const ID = "abcdef012345abcdef012345";
const STATE = "a".repeat(64);

function fixture() {
  const receipt = {
    schema: "janus.autonomy.snapshot.v1",
    current_phase: "P0.3", ecosystem_status: "AUTONOMY_PARTIAL",
    state_sha256: STATE, observation_id: ID,
    observed_at_utc: new Date().toISOString(),
    full_issue_162_acceptance: false, authority: {delta: 0},
    findings: [
      {phase:"P0.3", reason:"BEETLE_DELIVERY_PENDING", evidence:{total_pending:14}},
      {phase:"P0.5", reason:"SCOUT_MODEL_SYNTHESIS_DEGRADED", evidence:{snapshots:17,synthesis:0,expected:17}},
      {phase:"P0.4", reason:"PATCHES_WAITING", evidence:38}
    ],
    roadmap: [
      {phase:"P0.1",state:"DONE",objective:"first"},
      {phase:"P0.3",state:"ACTIVE",objective:"Beetle cloud recovery"}
    ],
    metrics:{
      native_model:{attempt_count:1701,promotion_count:61},
      self_writer:{accepted_pure_modules:9},
    },
    maintenance:{p02_proof:{sources:{}}},
  };
  const raw = Buffer.from(JSON.stringify(receipt), "utf8");
  const latest = {
    schema:"janus.autonomy.latest.v1",
    receipt_path:"data/autonomy_loop/receipts/" + ID + ".json",
    receipt_sha256:crypto.createHash("sha256").update(raw).digest("hex"),
    state_sha256:STATE, current_phase:"P0.3",
    ecosystem_status:"AUTONOMY_PARTIAL",
    last_observed_at_utc:receipt.observed_at_utc, full_issue_162_acceptance:false,
  };
  const checkpoint = {schema:"janus.autonomy.checkpoint.v1",current_phase:"P0.3",authority_delta:0};
  return {receipt,raw,latest,checkpoint};
}

function node() {
  const n = {
    children:[],textContent:"",className:"",disabled:false,href:"",
    classList:{toggle(){}},addEventListener(){},
    appendChild(child){this.children.push(child);return child;},
    removeChild(child){this.children.splice(this.children.indexOf(child),1);},
  };
  Object.defineProperty(n,"firstChild",{get(){return this.children[0];}});
  return n;
}

async function render(f, overrides = {}) {
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,node());return elements.get(id);};
  const document={
    hidden:false,getElementById:get,createElement:()=>node(),addEventListener(){},
  };
  const requests=[];
  const fetch=async url=>{
    requests.push(url);
    if(url.includes("/LATEST.json"))return {ok:true,json:async()=>f.latest};
    if(url.includes("/CHECKPOINT.json"))return {ok:true,json:async()=>f.checkpoint};
    if(url.includes("/receipts/"))return {ok:true,arrayBuffer:async()=>Uint8Array.from(f.raw).buffer};
    throw Error("UNEXPECTED_FETCH: "+url);
  };
  const sandbox = {
    document,fetch, navigator:{},location:{protocol:"http:"},
    crypto: overrides.crypto === false ? undefined : crypto.webcrypto,
    TextDecoder, console:{warn(){}},
    setInterval(){},setTimeout(){},
  };
  vm.runInNewContext(APP,sandbox,{filename:"app.js"});
  for(let i=0;i<250 && get("refresh").disabled;i++){
    await new Promise(setImmediate);
  }
  assert.equal(get("refresh").disabled,false,"refresh failed to settle");
  return {get,requests};
}

test("valid byte-pinned receipt renders live metrics from the same immutable record",async()=>{
  const f=fixture();
  const out=await render(f);
  assert.equal(out.get("status-value").textContent,"AUTONOMY_PARTIAL");
  assert.equal(out.get("phase-value").textContent,"P0.3");
  assert.equal(out.get("beetle-value").textContent,"14");
  assert.equal(out.get("patches").textContent,"38");
  assert.equal(out.get("modules").textContent,"9");
  assert.equal(out.get("phases").children.length,2);
  assert.equal(out.get("connection").textContent,"Байты receipt совпали с SHA-256");
  assert.equal(out.requests.filter(u=>u.includes("ROADMAP.md")).length,0);
});

test("tampered bytes, even with matching JSON fields, fail closed",async()=>{
  const f=fixture();
  const newObj={...f.receipt, findings:[...f.receipt.findings,{phase:"P1",reason:"INJECTED",evidence:1}]};
  f.raw=Buffer.from(JSON.stringify(newObj));
  const out=await render(f);
  assert.equal(out.get("status-value").textContent,"—");
  assert.equal(out.get("connection").textContent,"Нет проверенного snapshot");
  assert.equal(out.get("copy-hash").disabled,true);
});

test("a valid newly hashed receipt with different state digest is rejected",async()=>{
  const f=fixture();
  f.receipt.state_sha256="c".repeat(64);
  f.raw=Buffer.from(JSON.stringify(f.receipt));
  f.latest.receipt_sha256=crypto.createHash("sha256").update(f.raw).digest("hex");
  const out=await render(f);
  assert.equal(out.get("status-value").textContent,"—");
});

test("absent browser SHA-256 engine fails closed, never silently skips hashing",async()=>{
  const out=await render(fixture(),{crypto:false});
  assert.equal(out.get("status-value").textContent,"—");
  assert.equal(out.get("connection").textContent,"Нет проверенного snapshot");
});

test("snapshot observation id and timestamp remain bound to the pointer",async()=>{
  const f=fixture();
  f.latest.last_observed_at_utc="2010-01-01T00:00:00Z";
  const out=await render(f);
  assert.equal(out.get("status-value").textContent,"—");
});
