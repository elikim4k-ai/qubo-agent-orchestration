// builder.js — helpers for assembling the thesis
const {
  Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, BorderStyle, ShadingType, PageBreak, TabStopType, LevelFormat,
} = require("docx");

const FONT = "Georgia";
const MONO = "Consolas";

function runs(spec) {
  // spec: string | array of {t, b, i, sub, sup, mono}
  if (typeof spec === "string") return [new TextRun({ text: spec, font: FONT, size: 22 })];
  return spec.map(r => new TextRun({
    text: r.t, bold: !!r.b, italics: !!r.i,
    subScript: !!r.sub, superScript: !!r.sup,
    font: r.mono ? MONO : FONT, size: r.mono ? 20 : 22,
  }));
}

const h1 = (text, opts = {}) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  pageBreakBefore: opts.noBreak ? false : true,
  spacing: { before: 240, after: 240 },
  children: [new TextRun({ text, font: FONT, size: 34, bold: true, color: "1A1A1A" })],
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 300, after: 160 },
  children: [new TextRun({ text, font: FONT, size: 27, bold: true, color: "1A1A1A" })],
});

const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 240, after: 120 },
  children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: "333333" })],
});

const p = (spec, opts = {}) => new Paragraph({
  spacing: { after: 160, line: 336 },
  alignment: AlignmentType.JUSTIFIED,
  indent: opts.indent ? { left: 360 } : undefined,
  children: runs(spec),
});

// display equation, centred, with optional right-aligned tag like (3.2)
const eq = (spec, tag) => new Paragraph({
  spacing: { before: 120, after: 160 },
  alignment: AlignmentType.CENTER,
  tabStops: tag ? [{ type: TabStopType.RIGHT, position: 9360 }] : [],
  children: [
    ...(typeof spec === "string"
      ? [new TextRun({ text: spec, font: "Cambria Math", size: 22, italics: true })]
      : spec.map(r => new TextRun({
          text: r.t, italics: r.i !== false, bold: !!r.b,
          subScript: !!r.sub, superScript: !!r.sup,
          font: "Cambria Math", size: 22,
        }))),
    ...(tag ? [new TextRun({ text: "\t(" + tag + ")", font: FONT, size: 22 })] : []),
  ],
});

const bullets = (items) => items.map(it => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 100, line: 336 },
  alignment: AlignmentType.JUSTIFIED,
  children: runs(it),
}));

const numbered = (items, ref) => items.map(it => new Paragraph({
  numbering: { reference: ref, level: 0 },
  spacing: { after: 100, line: 336 },
  alignment: AlignmentType.JUSTIFIED,
  children: runs(it),
}));

const code = (lines) => lines.map(l => new Paragraph({
  spacing: { after: 20 },
  shading: { type: ShadingType.CLEAR, fill: "F4F4F4" },
  children: [new TextRun({ text: l.length ? l : " ", font: MONO, size: 18 })],
}));

const caption = (text) => new Paragraph({
  spacing: { before: 80, after: 240 },
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text, font: FONT, size: 20, italics: true, color: "444444" })],
});

// table: header array + rows array of arrays; widths in DXA summing to total
function table(header, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  const mkCell = (text, isHead) => new TableCell({
    width: { size: widths[0], type: WidthType.DXA }, // overridden per-cell below
    children: [new Paragraph({
      spacing: { before: 40, after: 40 },
      children: [new TextRun({ text: String(text), font: FONT, size: 20, bold: isHead })],
    })],
    shading: isHead ? { type: ShadingType.CLEAR, fill: "E8E4DC" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
  });
  const mkRow = (cells, isHead) => new TableRow({
    cantSplit: true,
    children: cells.map((c, idx) => {
      const cell = mkCell(c, isHead);
      cell.options = cell.options || {};
      return new TableCell({
        width: { size: widths[idx], type: WidthType.DXA },
        children: [new Paragraph({
          spacing: { before: 40, after: 40 },
          children: [new TextRun({ text: String(c), font: FONT, size: 20, bold: isHead })],
        })],
        shading: isHead ? { type: ShadingType.CLEAR, fill: "E8E4DC" } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
      });
    }),
    tableHeader: isHead,
  });
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [mkRow(header, true), ...rows.map(r => mkRow(r, false))],
  });
}

const spacer = () => new Paragraph({ spacing: { after: 120 }, children: [] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

module.exports = { h1, h2, h3, p, eq, bullets, numbered, code, caption, table, spacer, pageBreak, FONT, runs };
