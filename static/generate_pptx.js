const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'Facilim';
pres.title = 'Facilim — Interface Tableau de Bord';

// Brand colors (no # prefix)
const NAVY    = "1B3A6B";
const GREEN   = "2ECC9A";
const BG      = "F0F4F8";
const WHITE   = "FFFFFF";
const DARK_TXT = "1E293B";
const MID_TXT  = "475569";
const LIGHT_TXT = "94A3B8";
const CARD_BG  = "FFFFFF";
const CARD_BOR = "E8EDF3";
const ACCENT   = "2ECC9A";

const makeShadow = () => ({ type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.10 });

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 1 — TITRE
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // Top decorative bar (green)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.07,
    fill: { color: GREEN }, line: { color: GREEN }
  });

  // Big "F" logo circle
  s.addShape(pres.shapes.OVAL, {
    x: 0.65, y: 1.1, w: 1.1, h: 1.1,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("F", {
    x: 0.65, y: 1.1, w: 1.1, h: 1.1,
    fontSize: 36, bold: true, color: NAVY,
    align: "center", valign: "middle", margin: 0
  });

  // Facilim wordmark
  s.addText("Facilim", {
    x: 1.9, y: 1.1, w: 4, h: 1.1,
    fontSize: 40, bold: true, color: WHITE,
    align: "left", valign: "middle", margin: 0
  });

  // Subtitle
  s.addText("Interface Tableau de Bord", {
    x: 0.6, y: 2.5, w: 8.8, h: 0.8,
    fontSize: 28, bold: false, color: GREEN,
    align: "center", valign: "middle"
  });

  // Tagline
  s.addText("Simplifier la constitution des dossiers MDPH\npour les professionnels du handicap", {
    x: 0.6, y: 3.4, w: 8.8, h: 0.9,
    fontSize: 15, color: "A8C5E8",
    align: "center", valign: "middle"
  });

  // Chips
  const chips = ["B2B SaaS", "MDPH", "IA & WhatsApp", "RGPD / HDS"];
  chips.forEach((c, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 1.2 + i * 2.0, y: 4.5, w: 1.7, h: 0.38,
      fill: { color: "1D4A8A" }, line: { color: "2D5A9A" }, rectRadius: 0.08
    });
    s.addText(c, {
      x: 1.2 + i * 2.0, y: 4.5, w: 1.7, h: 0.38,
      fontSize: 10, color: GREEN, bold: true,
      align: "center", valign: "middle", margin: 0
    });
  });

  // Bottom bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.45, w: 10, h: 0.175,
    fill: { color: "152D56" }, line: { color: "152D56" }
  });
  s.addText("Confidentiel · 2026", {
    x: 0, y: 5.45, w: 10, h: 0.175,
    fontSize: 9, color: LIGHT_TXT, align: "center", valign: "middle", margin: 0
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 2 — LE PROBLÈME RÉSOLU
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  // Navy top strip
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Le problème résolu", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE,
    valign: "middle", margin: 0
  });

  // Left column — AVANT
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.4, y: 0.75, w: 4.3, h: 4.5,
    fill: { color: "FEF2F2" }, line: { color: "FCA5A5", pt: 1.5 },
    shadow: makeShadow()
  });
  s.addText("😓  Avant Facilim", {
    x: 0.5, y: 0.82, w: 4.1, h: 0.45,
    fontSize: 14, bold: true, color: "DC2626", align: "center"
  });
  const beforeItems = [
    "Formulaire CERFA de 16 pages à remplir manuellement",
    "Collecte fastidieuse des pièces justificatives",
    "Allers-retours répétés avec les familles",
    "Délais MDPH : 4 à 6 mois pour un dossier complet",
    "Charge administrative écrasante pour les éducateurs",
  ];
  beforeItems.forEach((item, i) => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.55, y: 1.35 + i * 0.64, w: 0.28, h: 0.28,
      fill: { color: "FCA5A5" }, line: { color: "FCA5A5" }
    });
    s.addText("✗", {
      x: 0.55, y: 1.35 + i * 0.64, w: 0.28, h: 0.28,
      fontSize: 11, bold: true, color: WHITE,
      align: "center", valign: "middle", margin: 0
    });
    s.addText(item, {
      x: 0.92, y: 1.35 + i * 0.64, w: 3.6, h: 0.5,
      fontSize: 11, color: DARK_TXT, valign: "middle"
    });
  });

  // Right column — APRÈS
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 0.75, w: 4.3, h: 4.5,
    fill: { color: CARD_BG }, line: { color: "6EE7B7", pt: 1.5 },
    shadow: makeShadow()
  });
  s.addText("✅  Avec Facilim", {
    x: 5.4, y: 0.82, w: 4.1, h: 0.45,
    fontSize: 14, bold: true, color: "059669", align: "center"
  });
  const afterItems = [
    "Bot WhatsApp guide la famille étape par étape",
    "IA pré-remplit automatiquement le CERFA 15692",
    "Relances automatiques (J+1, J+2, J+3)",
    "Score de complétude en temps réel",
    "Dossier complet envoyé par email en quelques jours",
  ];
  afterItems.forEach((item, i) => {
    s.addShape(pres.shapes.OVAL, {
      x: 5.42, y: 1.35 + i * 0.64, w: 0.28, h: 0.28,
      fill: { color: GREEN }, line: { color: GREEN }
    });
    s.addText("✓", {
      x: 5.42, y: 1.35 + i * 0.64, w: 0.28, h: 0.28,
      fontSize: 11, bold: true, color: NAVY,
      align: "center", valign: "middle", margin: 0
    });
    s.addText(item, {
      x: 5.79, y: 1.35 + i * 0.64, w: 3.65, h: 0.5,
      fontSize: 11, color: DARK_TXT, valign: "middle"
    });
  });

  // Arrow between
  s.addShape(pres.shapes.RECTANGLE, {
    x: 4.72, y: 2.7, w: 0.56, h: 0.3,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("→", {
    x: 4.72, y: 2.7, w: 0.56, h: 0.3,
    fontSize: 18, bold: true, color: WHITE,
    align: "center", valign: "middle", margin: 0
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 3 — VUE D'ENSEMBLE DU DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Vue d'ensemble — Tableau de bord", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Nav bar mockup
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.7, w: 9.4, h: 0.52,
    fill: { color: NAVY }, line: { color: "162D56" }, shadow: makeShadow()
  });
  s.addShape(pres.shapes.OVAL, {
    x: 0.45, y: 0.76, w: 0.38, h: 0.38,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("F", {
    x: 0.45, y: 0.76, w: 0.38, h: 0.38,
    fontSize: 13, bold: true, color: NAVY,
    align: "center", valign: "middle", margin: 0
  });
  s.addText("Facilim   |   Tableau de bord · Agents actifs", {
    x: 0.9, y: 0.76, w: 5.5, h: 0.38,
    fontSize: 10, color: "A8C5E8", valign: "middle", margin: 0
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 8.2, y: 0.79, w: 1.2, h: 0.34,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("+ Nouveau", {
    x: 8.2, y: 0.79, w: 1.2, h: 0.34,
    fontSize: 10, bold: true, color: NAVY,
    align: "center", valign: "middle", margin: 0
  });

  // 6 KPI cards — 2 rows × 3
  const kpis = [
    { label: "Total",     value: "12",  icon: "📁", color: NAVY,    bg: "EEF3FB" },
    { label: "En cours",  value: "5",   icon: "🔄", color: "0369A1", bg: "E0F2FE" },
    { label: "Incomplets",value: "3",   icon: "⚠️",  color: "D97706", bg: "FEF9C3" },
    { label: "Complétés", value: "4",   icon: "✅",  color: "059669", bg: "ECFDF5" },
    { label: "Urgents",   value: "1",   icon: "🔴", color: "DC2626", bg: "FEF2F2" },
    { label: "Bloqués",   value: "2",   icon: "🚫", color: "7C3AED", bg: "F5F3FF" },
  ];
  const cols = [0.3, 3.58, 6.85];
  const rows = [1.38, 2.72];
  kpis.forEach((k, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = cols[col];
    const y = rows[row];
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 3.0, h: 1.18,
      fill: { color: k.bg }, line: { color: CARD_BOR }, shadow: makeShadow()
    });
    s.addText(k.icon, { x: x + 0.15, y: y + 0.12, w: 0.6, h: 0.6, fontSize: 20, margin: 0 });
    s.addText(k.value, {
      x: x + 0.15, y: y + 0.62, w: 1.2, h: 0.48,
      fontSize: 26, bold: true, color: k.color, margin: 0
    });
    s.addText(k.label, {
      x: x + 1.5, y: y + 0.3, w: 1.4, h: 0.5,
      fontSize: 12, color: MID_TXT, valign: "bottom", margin: 0
    });
  });

  // Bottom note
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 4.05, w: 9.4, h: 0.42,
    fill: { color: "FEF9C3" }, line: { color: "FDE68A" }
  });
  s.addText("⚠️  Bannière d'attention automatique — alerte quand des dossiers incomplets nécessitent une action immédiate", {
    x: 0.4, y: 4.05, w: 9.2, h: 0.42,
    fontSize: 10.5, color: "92400E", valign: "middle", margin: 0
  });

  s.addText("Navigation sombre · 6 indicateurs clés · Alertes contextuelles", {
    x: 0, y: 4.62, w: 10, h: 0.55,
    fontSize: 11, color: MID_TXT, italic: true, align: "center", valign: "middle"
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 4 — GESTION DES DOSSIERS
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Gestion des dossiers", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Table header
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.65, w: 9.4, h: 0.4,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  const headers = ["Référence", "Famille", "Statut", "Score", "Relances", "Urgence", "Actions"];
  const hWidths = [1.3, 1.7, 1.3, 1.5, 0.9, 0.9, 1.7];
  let hx = 0.4;
  headers.forEach((h, i) => {
    s.addText(h, {
      x: hx, y: 0.68, w: hWidths[i], h: 0.35,
      fontSize: 9.5, bold: true, color: WHITE, valign: "middle", margin: 0
    });
    hx += hWidths[i];
  });

  // Dossier rows
  const dossiers = [
    { ref: "DOS-001", famille: "Martin A.", statut: "Complet",   statusColor: "059669", statusBg: "ECFDF5", score: 92, relances: 1, urgence: "Normale",  urgColor: "475569", urgBg: "F1F5F9" },
    { ref: "DOS-002", famille: "Dubois F.", statut: "Incomplet", statusColor: "D97706", statusBg: "FEF3C7", score: 48, relances: 3, urgence: "Haute",     urgColor: "DC2626", urgBg: "FEF2F2" },
    { ref: "DOS-003", famille: "Nait Ali K.", statut: "En cours", statusColor: "0369A1", statusBg: "DBEAFE", score: 67, relances: 2, urgence: "Normale",  urgColor: "475569", urgBg: "F1F5F9" },
    { ref: "DOS-004", famille: "Lemaire P.", statut: "Bloqué",   statusColor: "7C3AED", statusBg: "EDE9FE", score: 31, relances: 0, urgence: "Critique",  urgColor: "9A1515", urgBg: "FEE2E2" },
  ];

  dossiers.forEach((d, i) => {
    const y = 1.1 + i * 0.75;
    const bg = i % 2 === 0 ? WHITE : "F8FAFC";
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.3, y, w: 9.4, h: 0.68,
      fill: { color: bg }, line: { color: CARD_BOR }
    });

    // Ref
    s.addText(d.ref, { x: 0.4, y: y + 0.04, w: 1.3, h: 0.6, fontSize: 10, color: NAVY, bold: true, valign: "middle", margin: 0 });
    // Famille
    s.addText(d.famille, { x: 1.7, y: y + 0.04, w: 1.7, h: 0.6, fontSize: 10, color: DARK_TXT, valign: "middle", margin: 0 });
    // Statut badge
    s.addShape(pres.shapes.RECTANGLE, { x: 3.4, y: y + 0.17, w: 1.1, h: 0.34, fill: { color: d.statusBg }, line: { color: d.statusBg } });
    s.addText(d.statut, { x: 3.4, y: y + 0.17, w: 1.1, h: 0.34, fontSize: 9, bold: true, color: d.statusColor, align: "center", valign: "middle", margin: 0 });
    // Score bar background
    s.addShape(pres.shapes.RECTANGLE, { x: 4.55, y: y + 0.23, w: 1.3, h: 0.2, fill: { color: "E2E8F0" }, line: { color: "E2E8F0" } });
    // Score bar fill
    const barW = (d.score / 100) * 1.3;
    const barColor = d.score >= 70 ? "059669" : d.score >= 40 ? "D97706" : "DC2626";
    s.addShape(pres.shapes.RECTANGLE, { x: 4.55, y: y + 0.23, w: barW, h: 0.2, fill: { color: barColor }, line: { color: barColor } });
    s.addText(`${d.score}%`, { x: 5.9, y: y + 0.04, w: 0.5, h: 0.6, fontSize: 9.5, color: MID_TXT, valign: "middle", margin: 0 });
    // Relances
    s.addText(`${d.relances} ✉️`, { x: 6.45, y: y + 0.04, w: 0.9, h: 0.6, fontSize: 10, color: MID_TXT, align: "center", valign: "middle", margin: 0 });
    // Urgence badge
    s.addShape(pres.shapes.RECTANGLE, { x: 7.37, y: y + 0.17, w: 0.88, h: 0.34, fill: { color: d.urgBg }, line: { color: d.urgBg } });
    s.addText(d.urgence, { x: 7.37, y: y + 0.17, w: 0.88, h: 0.34, fontSize: 8.5, bold: true, color: d.urgColor, align: "center", valign: "middle", margin: 0 });
    // Actions
    const actions = ["Voir", "Enrichir", "Score"];
    actions.forEach((a, j) => {
      s.addShape(pres.shapes.RECTANGLE, {
        x: 8.3 + j * 0.38, y: y + 0.18, w: 0.33, h: 0.3,
        fill: { color: j === 0 ? NAVY : j === 1 ? GREEN : "6366F1" },
        line: { color: j === 0 ? NAVY : j === 1 ? GREEN : "6366F1" }
      });
      s.addText(a, {
        x: 8.3 + j * 0.38, y: y + 0.18, w: 0.33, h: 0.3,
        fontSize: 7.5, bold: true, color: j === 1 ? NAVY : WHITE,
        align: "center", valign: "middle", margin: 0
      });
    });
  });

  // Legend
  s.addText("Badges colorés par statut · Barre de progression score · Actions contextuelles par dossier", {
    x: 0, y: 5.15, w: 10, h: 0.38,
    fontSize: 10, color: MID_TXT, italic: true, align: "center", valign: "middle"
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 5 — GUIDE D'ACTION INTELLIGENT
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Guide d'action intelligent — Modal \"Voir\"", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Modal card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.72, w: 9.4, h: 4.68,
    fill: { color: WHITE }, line: { color: CARD_BOR }, shadow: makeShadow()
  });

  // Modal header
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.72, w: 9.4, h: 0.52,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("📋  DOS-002 · Dubois Françoise · Dossier incomplet", {
    x: 0.5, y: 0.72, w: 8.5, h: 0.52,
    fontSize: 13, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Score bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.45, y: 1.38, w: 9.1, h: 0.22,
    fill: { color: "E2E8F0" }, line: { color: "E2E8F0" }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.45, y: 1.38, w: 4.37, h: 0.22,
    fill: { color: "D97706" }, line: { color: "D97706" }
  });
  s.addText("Score de complétude : 48 %   →   potentiel estimé : 82 % après enrichissement", {
    x: 0.45, y: 1.64, w: 9.1, h: 0.3,
    fontSize: 10, color: "D97706", italic: true, margin: 0
  });

  // Checklist
  const checks = [
    { ok: true,  label: "Identité & contact bénéficiaire" },
    { ok: true,  label: "Type de demande (renouvellement AEEH)" },
    { ok: false, label: "Situation professionnelle / scolaire manquante" },
    { ok: false, label: "Certificat médical (à transmettre par messagerie sécurisée)" },
    { ok: false, label: "Justificatif de domicile non fourni" },
  ];
  checks.forEach((c, i) => {
    const y = 2.05 + i * 0.46;
    s.addShape(pres.shapes.OVAL, {
      x: 0.5, y: y + 0.06, w: 0.28, h: 0.28,
      fill: { color: c.ok ? "ECFDF5" : "FEF2F2" },
      line: { color: c.ok ? "059669" : "DC2626" }
    });
    s.addText(c.ok ? "✓" : "✗", {
      x: 0.5, y: y + 0.06, w: 0.28, h: 0.28,
      fontSize: 10, bold: true, color: c.ok ? "059669" : "DC2626",
      align: "center", valign: "middle", margin: 0
    });
    s.addText(c.label, {
      x: 0.88, y, w: 5.0, h: 0.42,
      fontSize: 11, color: c.ok ? "059669" : DARK_TXT, valign: "middle", margin: 0
    });
    if (!c.ok) {
      const btnColor = c.label.includes("messagerie") ? "D97706" : GREEN;
      const btnText = c.label.includes("messagerie") ? "Email sécurisé" : c.label.includes("domicile") ? "Relancer" : "Enrichir";
      s.addShape(pres.shapes.RECTANGLE, {
        x: 5.95, y: y + 0.06, w: 1.2, h: 0.3,
        fill: { color: btnColor }, line: { color: btnColor }
      });
      s.addText(btnText, {
        x: 5.95, y: y + 0.06, w: 1.2, h: 0.3,
        fontSize: 9, bold: true, color: c.label.includes("messagerie") ? WHITE : NAVY,
        align: "center", valign: "middle", margin: 0
      });
    }
  });

  // Action recommandée box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.45, y: 4.48, w: 9.1, h: 0.7,
    fill: { color: "F0FDF4" }, line: { color: GREEN, pt: 2 }
  });
  s.addText("⚡  Action recommandée : Relancer la famille par WhatsApp pour obtenir la situation professionnelle", {
    x: 0.6, y: 4.53, w: 6.5, h: 0.6,
    fontSize: 11, color: "065F46", valign: "middle", margin: 0
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.25, y: 4.55, w: 2.15, h: 0.45,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("▶  Relancer maintenant", {
    x: 7.25, y: 4.55, w: 2.15, h: 0.45,
    fontSize: 10, bold: true, color: NAVY,
    align: "center", valign: "middle", margin: 0
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 6 — COLLECTE WHATSAPP IA
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Collecte WhatsApp IA — FALC & conversationnelle", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Phone mockup
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.4, y: 0.72, w: 3.3, h: 4.68,
    fill: { color: "1A1A2E" }, line: { color: "2D2D44" }, rectRadius: 0.25
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 1.0, w: 3.0, h: 4.1,
    fill: { color: "ECE5DD" }, line: { color: "ECE5DD" }
  });

  // WA header
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 1.0, w: 3.0, h: 0.42,
    fill: { color: "075E54" }, line: { color: "075E54" }
  });
  s.addText("🤖 Bot Facilim · WhatsApp", {
    x: 0.6, y: 1.0, w: 2.9, h: 0.42,
    fontSize: 9, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Messages
  const msgs = [
    { from: "bot", text: "Bonjour ! Je suis le bot Facilim. Je vais vous aider à préparer le dossier MDPH. Comment s'appelle la personne concernée ?" },
    { from: "user", text: "Dubois Françoise" },
    { from: "bot", text: "Merci ! Quelle est sa date de naissance ?" },
    { from: "user", text: "12/03/1978" },
    { from: "bot", text: "Parfait. S'agit-il d'une première demande ou d'un renouvellement ?" },
    { from: "user", text: "Renouvellement" },
  ];
  let my = 1.5;
  msgs.forEach((m) => {
    const isBot = m.from === "bot";
    const boxW = 2.3;
    const bx = isBot ? 0.6 : 1.25;
    const bg = isBot ? WHITE : "DCF8C6";
    const textLen = m.text.length;
    const boxH = textLen > 60 ? 0.72 : 0.45;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: bx, y: my, w: boxW, h: boxH,
      fill: { color: bg }, line: { color: bg }, rectRadius: 0.06
    });
    s.addText(m.text, {
      x: bx + 0.05, y: my, w: boxW - 0.1, h: boxH,
      fontSize: 7.5, color: DARK_TXT, valign: "middle"
    });
    my += boxH + 0.1;
  });

  // Right side — feature list
  const features = [
    { icon: "🗣️", title: "FALC", desc: "Questions simples, vocabulaire adapté aux familles" },
    { icon: "🔄", title: "Relances auto", desc: "Mathilde relance J+1, J+2, J+3 si pas de réponse" },
    { icon: "🔒", title: "Données médicales", desc: "Redirigées vers email sécurisé — jamais via WhatsApp" },
    { icon: "🧠", title: "IA contextuelle", desc: "Mémorise les réponses, ne re-pose jamais les mêmes questions" },
    { icon: "📄", title: "CERFA auto", desc: "Réponses → formulaire 15692*01 pré-rempli automatiquement" },
  ];
  features.forEach((f, i) => {
    const y = 0.78 + i * 0.87;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 4.0, y, w: 5.7, h: 0.75,
      fill: { color: WHITE }, line: { color: CARD_BOR }, shadow: makeShadow()
    });
    s.addShape(pres.shapes.OVAL, {
      x: 4.12, y: y + 0.13, w: 0.48, h: 0.48,
      fill: { color: "EEF3FB" }, line: { color: "EEF3FB" }
    });
    s.addText(f.icon, { x: 4.12, y: y + 0.13, w: 0.48, h: 0.48, fontSize: 16, align: "center", valign: "middle", margin: 0 });
    s.addText(f.title, { x: 4.7, y: y + 0.08, w: 4.9, h: 0.3, fontSize: 12, bold: true, color: NAVY, margin: 0 });
    s.addText(f.desc, { x: 4.7, y: y + 0.38, w: 4.9, h: 0.3, fontSize: 10, color: MID_TXT, margin: 0 });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 7 — AGENTS IA EN ARRIÈRE-PLAN
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // Top label
  s.addText("Agents IA en arrière-plan", {
    x: 0, y: 0.18, w: 10, h: 0.5,
    fontSize: 22, bold: true, color: WHITE, align: "center"
  });
  s.addText("Une infrastructure multi-agents orchestre chaque dossier de façon autonome", {
    x: 0, y: 0.68, w: 10, h: 0.32,
    fontSize: 12, color: "A8C5E8", align: "center"
  });

  // 4 agent cards
  const agents = [
    {
      name: "Mathilde (N0)",
      icon: "🔔",
      color: "3B82F6",
      bg: "1D3461",
      role: "Relances automatiques",
      tasks: ["Relance J+1 si pas de réponse", "Relance J+2 avec reformulation", "Relance J+3 alerte éducateur", "Gestion des désinscriptions"],
    },
    {
      name: "Bot WhatsApp",
      icon: "💬",
      color: GREEN,
      bg: "1A3D2E",
      role: "Collecte conversationnelle",
      tasks: ["Questions FALC adaptées", "Extraction réponses CERFA", "Validation format données", "Mémoire inter-sessions"],
    },
    {
      name: "Analyse CNSA",
      icon: "⚖️",
      color: "F59E0B",
      bg: "3D2E10",
      role: "Scoring multi-agents",
      tasks: ["Expert GEVA : évaluation besoins", "Juriste : droits applicables", "Coordinateur : score global", "Identification éléments manquants"],
    },
    {
      name: "Générateur CERFA",
      icon: "📄",
      color: "A78BFA",
      bg: "2D1B4E",
      role: "Pré-remplissage CERFA 15692",
      tasks: ["Mapping réponses → champs PDF", "Validation cohérence données", "Génération CERFA 15692*01", "Envoi email dossier complet"],
    },
  ];
  agents.forEach((a, i) => {
    const x = 0.3 + i * 2.38;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.15, w: 2.2, h: 4.15,
      fill: { color: a.bg }, line: { color: a.color, pt: 1.5 }, shadow: makeShadow()
    });
    // Icon circle
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.7, y: 1.3, w: 0.78, h: 0.78,
      fill: { color: a.color }, line: { color: a.color }
    });
    s.addText(a.icon, {
      x: x + 0.7, y: 1.3, w: 0.78, h: 0.78,
      fontSize: 22, align: "center", valign: "middle", margin: 0
    });
    s.addText(a.name, {
      x: x + 0.1, y: 2.18, w: 2.0, h: 0.4,
      fontSize: 11, bold: true, color: a.color, align: "center"
    });
    s.addText(a.role, {
      x: x + 0.1, y: 2.55, w: 2.0, h: 0.32,
      fontSize: 9, color: "A8C5E8", align: "center", italic: true
    });
    a.tasks.forEach((t, j) => {
      s.addShape(pres.shapes.RECTANGLE, {
        x: x + 0.15, y: 2.98 + j * 0.3, w: 0.06, h: 0.14,
        fill: { color: a.color }, line: { color: a.color }
      });
      s.addText(t, {
        x: x + 0.27, y: 2.95 + j * 0.3, w: 1.85, h: 0.26,
        fontSize: 9, color: "CBD5E1", valign: "middle", margin: 0
      });
    });
  });

  // Bottom connector arrows
  [1, 2, 3].forEach(i => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.3 + i * 2.38 - 0.16, y: 3.15, w: 0.18, h: 0.14,
      fill: { color: GREEN }, line: { color: GREEN }
    });
    s.addText("→", {
      x: 0.3 + i * 2.38 - 0.18, y: 3.1, w: 0.22, h: 0.22,
      fontSize: 12, bold: true, color: GREEN,
      align: "center", valign: "middle", margin: 0
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 8 — SÉCURITÉ & CONFORMITÉ
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Sécurité & conformité — RGPD / HDS", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  const secItems = [
    {
      icon: "🔒",
      title: "Données médicales protégées",
      color: "DC2626",
      bg: "FEF2F2",
      border: "FCA5A5",
      points: [
        "Art. 9 RGPD : données de santé = catégorie spéciale",
        "NIR, diagnostic, traitements → JAMAIS via WhatsApp",
        "Transmission uniquement par messagerie sécurisée ou email chiffré",
        "Aucun stockage santé chez Meta ou dans les logs",
      ],
    },
    {
      icon: "🏥",
      title: "Hébergement Données de Santé (HDS)",
      color: "0369A1",
      bg: "EFF6FF",
      border: "BAE6FD",
      points: [
        "Infrastructure certifiée HDS pour les données médicales",
        "Cloisonnement strict données admin / données santé",
        "Chiffrement au repos et en transit (TLS 1.3)",
        "Traçabilité audit complète (trail immuable)",
      ],
    },
    {
      icon: "📋",
      title: "RGPD — Droits des personnes",
      color: "059669",
      bg: "F0FDF4",
      border: "86EFAC",
      points: [
        "Droit d'accès, rectification et effacement (Art. 17)",
        "Durée de conservation : 5 ans après fin accompagnement",
        "Consentement explicite avant collecte WhatsApp",
        "Registre des traitements à jour",
      ],
    },
    {
      icon: "🛡️",
      title: "Architecture sécurisée",
      color: "7C3AED",
      bg: "F5F3FF",
      border: "C4B5FD",
      points: [
        "Row Level Security (RLS) PostgreSQL par établissement",
        "Authentification JWT + refresh tokens sécurisés",
        "Webhook WhatsApp validé par signature HMAC-SHA256",
        "Railway + pgcrypto pour chiffrement colonne sensibles",
      ],
    },
  ];

  const positions = [[0.3, 0.72], [5.15, 0.72], [0.3, 2.95], [5.15, 2.95]];
  secItems.forEach((item, i) => {
    const [x, y] = positions[i];
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.7, h: 2.1,
      fill: { color: item.bg }, line: { color: item.border }, shadow: makeShadow()
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.15, y: y + 0.12, w: 0.5, h: 0.5,
      fill: { color: item.color }, line: { color: item.color }
    });
    s.addText(item.icon, {
      x: x + 0.15, y: y + 0.12, w: 0.5, h: 0.5,
      fontSize: 16, align: "center", valign: "middle", margin: 0
    });
    s.addText(item.title, {
      x: x + 0.73, y: y + 0.12, w: 3.85, h: 0.5,
      fontSize: 12, bold: true, color: item.color, valign: "middle", margin: 0
    });
    item.points.forEach((p, j) => {
      s.addText("·  " + p, {
        x: x + 0.2, y: y + 0.68 + j * 0.33, w: 4.35, h: 0.3,
        fontSize: 9.5, color: DARK_TXT, margin: 0
      });
    });
  });

  s.addText("Zéro donnée de santé chez Meta · Consentement explicite · Droit à l'effacement Art. 17", {
    x: 0, y: 5.2, w: 10, h: 0.32,
    fontSize: 10, color: MID_TXT, italic: true, align: "center"
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 9 — RÉSULTATS & MÉTRIQUES
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.55,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  s.addText("Résultats & métriques clés", {
    x: 0.5, y: 0, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: WHITE, valign: "middle", margin: 0
  });

  // Big stat cards
  const stats = [
    { value: "-70%", label: "Temps de constitution\ndu dossier", icon: "⏱️", color: NAVY, bg: "EEF3FB" },
    { value: "92%",  label: "Taux de réponse\nfamilles (WhatsApp)", icon: "💬", color: "059669", bg: "ECFDF5" },
    { value: "3j",   label: "Délai moyen\ndossier complet", icon: "🚀", color: "D97706", bg: "FEF9C3" },
    { value: "100%", label: "CERFA pré-rempli\nautomatiquement", icon: "📄", color: "7C3AED", bg: "F5F3FF" },
  ];
  stats.forEach((st, i) => {
    const x = 0.3 + i * 2.38;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 0.75, w: 2.2, h: 2.2,
      fill: { color: st.bg }, line: { color: CARD_BOR }, shadow: makeShadow()
    });
    s.addText(st.icon, { x, y: 0.88, w: 2.2, h: 0.55, fontSize: 26, align: "center" });
    s.addText(st.value, {
      x, y: 1.45, w: 2.2, h: 0.72,
      fontSize: 36, bold: true, color: st.color, align: "center"
    });
    s.addText(st.label, {
      x: x + 0.1, y: 2.18, w: 2.0, h: 0.65,
      fontSize: 10, color: MID_TXT, align: "center"
    });
  });

  // Donut chart — Score moyen complétude
  s.addChart(pres.charts.DOUGHNUT, [{
    name: "Complétude",
    labels: ["Complété", "Restant"],
    values: [68, 32],
  }], {
    x: 0.3, y: 3.15, w: 3.2, h: 2.15,
    chartColors: [GREEN, "E2E8F0"],
    showPercent: false,
    showLegend: true,
    legendPos: "b",
    legendFontSize: 9,
    legendColor: MID_TXT,
    chartArea: { fill: { color: BG } },
    holeSize: 60,
    showTitle: true,
    title: "Score moyen complétude",
    titleFontSize: 11,
    titleColor: DARK_TXT,
  });

  // Bar chart — Dossiers par statut
  s.addChart(pres.charts.BAR, [{
    name: "Dossiers",
    labels: ["Complets", "En cours", "Incomplets", "Bloqués"],
    values: [18, 12, 8, 4],
  }], {
    x: 3.7, y: 3.15, w: 5.9, h: 2.15,
    barDir: "col",
    chartColors: ["059669", "0369A1", "D97706", "7C3AED"],
    chartArea: { fill: { color: BG } },
    valGridLine: { color: "E2E8F0", size: 0.5 },
    catGridLine: { style: "none" },
    catAxisLabelColor: MID_TXT,
    valAxisLabelColor: MID_TXT,
    showValue: true,
    dataLabelPosition: "outEnd",
    dataLabelColor: DARK_TXT,
    showLegend: false,
    showTitle: true,
    title: "Répartition des dossiers",
    titleFontSize: 11,
    titleColor: DARK_TXT,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SLIDE 10 — CONCLUSION / CONTACT
// ─────────────────────────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.45, w: 10, h: 0.18,
    fill: { color: GREEN }, line: { color: GREEN }
  });

  // Big F logo
  s.addShape(pres.shapes.OVAL, {
    x: 4.1, y: 0.35, w: 1.8, h: 1.8,
    fill: { color: GREEN }, line: { color: GREEN }
  });
  s.addText("F", {
    x: 4.1, y: 0.35, w: 1.8, h: 1.8,
    fontSize: 60, bold: true, color: NAVY,
    align: "center", valign: "middle", margin: 0
  });

  s.addText("Facilim", {
    x: 0, y: 2.3, w: 10, h: 0.65,
    fontSize: 36, bold: true, color: WHITE, align: "center"
  });
  s.addText("L'infrastructure qui libère les éducateurs spécialisés\nde la charge administrative MDPH", {
    x: 1, y: 3.0, w: 8, h: 0.75,
    fontSize: 14, color: "A8C5E8", align: "center"
  });

  // Contact chips
  const contacts = [
    { icon: "📧", label: "contact@facilim.fr" },
    { icon: "💻", label: "app.facilim.fr" },
    { icon: "📍", label: "France · Accès sur demande" },
  ];
  contacts.forEach((c, i) => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.9 + i * 2.85, y: 4.0, w: 2.6, h: 0.52,
      fill: { color: "1D4A8A" }, line: { color: "2D5A9A" }
    });
    s.addText(`${c.icon}  ${c.label}`, {
      x: 0.9 + i * 2.85, y: 4.0, w: 2.6, h: 0.52,
      fontSize: 11, color: GREEN, align: "center", valign: "middle", bold: true
    });
  });

  s.addText("Facilim est une solution B2B réservée aux établissements ESSMS (IME, SESSAD, ESAT, SAVS, SAMSAH)", {
    x: 0.5, y: 4.72, w: 9, h: 0.35,
    fontSize: 9, color: LIGHT_TXT, align: "center", italic: true
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// WRITE FILE
// ─────────────────────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "C:\\Users\\Nassim KAMLI\\mdph-backbone\\static\\Facilim_Dashboard_Presentation.pptx" })
  .then(() => console.log("✅ Présentation générée avec succès !"))
  .catch(err => { console.error("❌ Erreur :", err); process.exit(1); });
