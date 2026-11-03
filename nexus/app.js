"use strict";

/*
 * JANUS NEXUS v1 — public, read-only evidence viewer.
 * Important: "source mentioned in receipt" is NOT a service-health assertion.
 * No tokens, no GitHub write API, no model permissions, no mutation endpoints.
 */
(() => {
  const ROOT = "../data/autonomy_loop/";
  const SOURCE_URL = "https://github.com/Hawkar-usls/janus-meta-registry";
  const RECEIPT_RE = /^data\/autonomy_loop\/receipts\/[0-9a-f]{24}\.json$/;
  const HASH_RE = /^[a-f0-9]{64}$/i;
  const el = id => document.getElementById(id);
  const fmtCount = n => typeof n === "number" && Number.isSafeInteger(n) && n >= 0
    ? n.toLocaleString("ru-RU") : "—";
  const value = (v, fallback = "—") => v === undefined || v === null || v === "" ? fallback : String(v);

  const organs = [
    { name: "DEMIURGE", icon: "◈", role: "Council · модель и решения", source: "council", node: "node-demiurge" },
    { name: "AURA Oracle", icon: "✧", role: "Гипотезы и исследовательский контур", source: "aura", node: "node-aura" },
    { name: "BEETLE", icon: "⌁", role: "Транспорт и доставка", source: "beetle", node: "node-beetle" },
    { name: "HRAiN", icon: "▥", role: "Память / привязка исходника", source: "hrain", node: "node-hrain" },
    { name: "Cloud HOME", icon: "⌂", role: "Исполнение в среде — требует отдельного аттестата", source: null, node: "node-home" },
    { name: "DADDY_KEYMASTER", icon: "◇", role: "Пул workers / CAS champion — нет runtime-аттестата", source: null, node: "node-keymaster" }
  ];

  let isBusy = false;
  let lastHash = null;

  function set(id, v) { const n = el(id); if (n) n.textContent = value(v); }
  function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function tag(name, className, content) {
    const n = document.createElement(name);
    if (className) n.className = className;
    if (content !== undefined) n.textContent = String(content);
    return n;
  }
  function localTime(iso) {
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) return "не указано";
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: "Europe/Kyiv", day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: false
    }).format(d) + " (Киев)";
  }
  function stale(iso) {
    const t = new Date(iso).getTime();
    return !Number.isFinite(t) || t > Date.now() + 5 * 60 * 1000 || Date.now() - t > 2 * 60 * 60 * 1000;
  }
  function linkForReceipt(path) {
    return RECEIPT_RE.test(path || "") ? "../" + path : null;
  }
  function setConnection(mode, label) {
    const n = el("connection");
    n.className = "connection " + mode;
    n.textContent = label;
  }
  function safeEvidence(v) {
    if (v === null || v === undefined) return "НЕ УКАЗАНО";
    if (typeof v === "string") return v.slice(0, 240);
    try { return JSON.stringify(v).slice(0, 300); }
    catch (_) { return "НЕЧИТАЕМО"; }
  }

  function renderOrgans(receipt) {
    const list = el("organ-list");
    clearNode(list);
    const sources = receipt && receipt.maintenance && receipt.maintenance.p02_proof
      && receipt.maintenance.p02_proof.sources || {};
    const findings = Array.isArray(receipt && receipt.findings) ? receipt.findings : [];
    const pendingBeetle = findings.some(f => f && f.reason === "BEETLE_DELIVERY_PENDING");

    for (const organ of organs) {
      const hasSource = organ.source && sources[organ.source] && typeof sources[organ.source].commit_sha === "string";
      const warned = organ.name === "BEETLE" && pendingBeetle;
      const state = warned ? "ДОСТАВКА ОЖИДАЕТ"
        : hasSource ? "ИСТОЧНИК УКАЗАН" : "НЕ ПОДТВЕРЖДЕНО";
      const cssState = warned ? "warned" : hasSource ? "attested" : "";

      const row = tag("div", "organ-row");
      const meta = tag("div", "organ-meta");
      meta.appendChild(tag("span", "organ-icon", organ.icon));
      const detail = tag("div", "");
      detail.appendChild(tag("span", "organ-title", organ.name));
      detail.appendChild(tag("span", "organ-role", organ.role));
      meta.appendChild(detail);
      row.appendChild(meta);
      row.appendChild(tag("span", "organ-state " + cssState, state));
      list.appendChild(row);

      const node = el(organ.node);
      if (node) node.classList.toggle("attested", !!hasSource && !warned);
      if (node) node.classList.toggle("warned", warned);
    }
  }

  function renderFindings(receipt) {
    const list = el("findings");
    clearNode(list);
    const findings = Array.isArray(receipt && receipt.findings)
      ? receipt.findings.slice(0, 30) : [];
    if (!findings.length) {
      list.appendChild(tag("div", "empty", "В последнем receipt нет открытых наблюдений"));
      return;
    }
    for (const f of findings) {
      if (!f || typeof f !== "object") continue;
      const row = tag("div", "finding-row");
      const left = tag("div", "");
      left.appendChild(tag("span", "finding-reason", value(f.reason, "UNKNOWN")));
      left.appendChild(tag("span", "finding-phase", value(f.phase, "—")));
      row.appendChild(left);
      row.appendChild(tag("div", "finding-evidence", safeEvidence(f.evidence)));
      list.appendChild(row);
    }
  }

  function renderPhases(text) {
    const list = el("phases");
    clearNode(list);
    const rows = [];
    for (const line of String(text || "").split("\n")) {
      const match = line.match(/^\|\s*\d+\s*\|\s*([A-Z][A-Z0-9.]*)\s*\|\s*([A-Z_]+)\s*\|\s*(.+?)\s*\|\s*$/);
      if (match) rows.push({ id: match[1], state: match[2], goal: match[3] });
    }
    if (!rows.length) {
      list.appendChild(tag("div", "empty", "Не удалось проверить дорожную карту"));
      return;
    }
    for (const phase of rows.slice(0, 12)) {
      const row = tag("div", "phase-row");
      row.appendChild(tag("span", "phase-id", phase.id));
      const goal = phase.goal.replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g, "$1");
      row.appendChild(tag("span", "phase-target", goal.slice(0, 180)));
      const kind = phase.state === "DONE" ? "done" : phase.state.includes("ACTIVE") ? "active" : "";
      row.appendChild(tag("span", "phase-status " + kind, phase.state));
      list.appendChild(row);
    }
  }

  function roadmapMetrics(text) {
    const match = String(text || "").match(new RegExp("`{3}json\\s*([\\s\\S]*?)\\s*`{3}", "i"));
    if (!match) return {};
    try { return JSON.parse(match[1]); } catch (_) { return {}; }
  }

  function renderEvidence(latest, checkpoint, receipt, roadmap) {
    const observedAt = latest.last_observed_at_utc;
    set("observed", localTime(observedAt));
    set("checked", localTime(new Date().toISOString()));
    set("status-value", latest.ecosystem_status);
    set("phase-value", latest.current_phase);
    set("status-sub", stale(observedAt) ? "Устаревший snapshot · не LIVE"
      : "Из последнего публичного snapshot");
    if (checkpoint && checkpoint.current_phase && checkpoint.current_phase !== latest.current_phase) {
      set("status-sub", "ПРЕДУПРЕЖДЕНИЕ: фазы источников расходятся");
    }

    const findings = Array.isArray(receipt.findings) ? receipt.findings : [];
    const beetle = findings.find(f => f && f.reason === "BEETLE_DELIVERY_PENDING");
    const scouts = findings.find(f => f && f.reason === "SCOUT_MODEL_SYNTHESIS_DEGRADED");
    set("beetle-value", fmtCount(beetle && beetle.evidence && beetle.evidence.total_pending));
    set("beetle-sub", beetle ? "Ожидающие доставки, не подтверждение потерь" : "Свидетельство отсутствует");
    if (scouts && scouts.evidence) {
      set("scout-value", fmtCount(scouts.evidence.synthesis) + " / " + fmtCount(scouts.evidence.expected));
      set("scout-sub", "Снимков: " + fmtCount(scouts.evidence.snapshots));
    } else {
      set("scout-value", "—");
      set("scout-sub", "Свидетельство отсутствует");
    }

    const metrics = roadmapMetrics(roadmap);
    const patchFinding = findings.find(f => f && f.reason === "PATCHES_WAITING");
    set("patches", fmtCount(patchFinding && patchFinding.evidence));
    set("modules", fmtCount(metrics.self_writer && metrics.self_writer.accepted_pure_modules));
    set("training", fmtCount(metrics.native_model && metrics.native_model.attempt_count));
    set("promotions", fmtCount(metrics.native_model && metrics.native_model.promotion_count));
    set("gate-detail", latest.full_issue_162_acceptance === true
      ? "Issue #162 отмечен принятым в snapshot; последующие уровни проверяются отдельно."
      : "Issue #162 не принят полностью. Переход к FULL автономности не доказан.");

    lastHash = HASH_RE.test(latest.state_sha256 || "") ? latest.state_sha256 : null;
    set("state-hash", lastHash || "недоступен");
    el("copy-hash").disabled = !lastHash;

    const receiptHref = linkForReceipt(latest.receipt_path);
    if (receiptHref) el("receipt-link").href = receiptHref;
    renderOrgans(receipt);
    renderFindings(receipt);
    renderPhases(roadmap);
  }

  function resetDashboard(message) {
    for (const id of ["observed","checked","status-value","phase-value","beetle-value","scout-value",
      "patches","modules","training","promotions","state-hash"]) set(id, "—");
    set("status-sub", message);
    set("beetle-sub", "Свидетельство не загружено");
    set("scout-sub", "Свидетельство не загружено");
    set("gate-detail", "Нет проверенного snapshot. Нельзя утверждать, что система работает.");
    lastHash = null;
    el("copy-hash").disabled = true;
    renderOrgans(null);
    renderFindings(null);
    renderPhases("");
  }

  async function read(url, asText = false) {
    const separator = url.includes("?") ? "&" : "?";
    const res = await fetch(url + separator + "ts=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status + ": " + url);
    return asText ? res.text() : res.json();
  }

  async function refresh() {
    if (isBusy) return;
    isBusy = true;
    el("refresh").disabled = true;
    setConnection("pending", "Чтение публичных данных");
    try {
      const [latest, checkpoint, roadmap] = await Promise.all([
        read(ROOT + "LATEST.json"), read(ROOT + "CHECKPOINT.json"),
        read(ROOT + "ROADMAP.md", true)
      ]);
      if (!latest || latest.schema !== "janus.autonomy.latest.v1"
          || typeof latest.current_phase !== "string"
          || typeof latest.ecosystem_status !== "string"
          || !linkForReceipt(latest.receipt_path)) {
        throw new Error("Invalid LATEST schema or receipt path");
      }
      const receipt = await read(linkForReceipt(latest.receipt_path));
      if (!receipt || receipt.current_phase !== latest.current_phase
          || receipt.ecosystem_status !== latest.ecosystem_status) {
        throw new Error("LATEST / receipt mismatch");
      }
      renderEvidence(latest, checkpoint, receipt, roadmap);
      const drift = checkpoint && checkpoint.current_phase && checkpoint.current_phase !== latest.current_phase;
      setConnection(drift ? "warning" : stale(latest.last_observed_at_utc) ? "warning" : "ok",
        drift ? "Несовпадение фаз" : stale(latest.last_observed_at_utc) ? "Устаревший snapshot" : "Свидетельство загружено");
    } catch (err) {
      console.warn("JANUS NEXUS: public evidence unavailable", err);
      resetDashboard("Сбой чтения данных · статус неизвестен");
      setConnection("error", "Нет проверенного snapshot");
    } finally {
      isBusy = false;
      el("refresh").disabled = false;
    }
  }

  el("refresh").addEventListener("click", refresh);
  el("copy-hash").addEventListener("click", async () => {
    if (!lastHash) return;
    try {
      await navigator.clipboard.writeText(lastHash);
      el("copy-hash").textContent = "Скопировано";
      setTimeout(() => { el("copy-hash").textContent = "Копировать"; }, 1800);
    } catch (_) { el("copy-hash").textContent = "Недоступно"; }
  });
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
  resetDashboard("Ожидание публичного snapshot");
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 120000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
