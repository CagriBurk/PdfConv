import Konva from "konva";
import { FONT_CSS } from "../fonts";

export { FONT_CSS };

/**
 * Editör nesneleri. Koordinatlar sunucuyla aynı "görünüm" uzayında: ekranda görülen sayfa,
 * sol üst (0, 0), y aşağı, PDF noktası (pdf.js ölçek 1). Ekran büyütmesi yalnızca çizimde.
 * Kutulu nesnelerde (x, y, w, h) döndürülmemiş kutu, `rotation` merkez etrafında saat yönünde.
 */

export type Tool =
  | "select"
  | "text"
  | "image"
  | "signature"
  | "highlight"
  | "rect"
  | "ellipse"
  | "line"
  | "arrow"
  | "redact"
  | "whiteout";

interface Base {
  id: string;
  page: number;
}

interface Box extends Base {
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
}

export type Align = "left" | "center" | "right" | "justify";

export interface TextObj extends Box {
  kind: "text";
  text: string;
  font: string;
  bold: boolean;
  size: number;
  color: string;
  align: Align;
  opacity: number;
}

export interface ImageObj extends Box {
  kind: "image";
  asset: string;
  opacity: number;
  signature: boolean;
}

export interface HighlightObj extends Box {
  kind: "highlight";
  color: string;
}

export interface ShapeObj extends Box {
  kind: "rect" | "ellipse";
  stroke: string | null;
  fill: string | null;
  width: number;
  opacity: number;
}

export interface LineObj extends Base {
  kind: "line" | "arrow";
  points: [number, number, number, number];
  stroke: string;
  width: number;
  opacity: number;
}

export interface CoverObj extends Box {
  kind: "redact" | "whiteout";
  color: string;
}

export type EditorObj = TextObj | ImageObj | HighlightObj | ShapeObj | LineObj | CoverObj;
export type BoxObj = Exclude<EditorObj, LineObj>;

export const isBox = (o: EditorObj): o is BoxObj => o.kind !== "line" && o.kind !== "arrow";
/** Sunucu bu türleri döndüremez (karartma/vurgu her zaman eksen hizalı). */
export const canRotate = (o: EditorObj) => ["text", "image", "rect", "ellipse"].includes(o.kind);

export const LINE_HEIGHT = 1.2;

let seq = 0;
export const newId = () => `o${Date.now().toString(36)}${++seq}`;

/** Yazının bu genişlikte kaç nokta yükseklik tutacağı (Konva aynı satır kaydırmayı yapar). */
export function measureText(o: Pick<TextObj, "text" | "font" | "bold" | "size" | "w" | "align">): number {
  const node = new Konva.Text({
    text: o.text || " ",
    width: o.w,
    fontFamily: FONT_CSS[o.font] ?? "sans-serif",
    fontStyle: o.bold ? "bold" : "normal",
    fontSize: o.size,
    lineHeight: LINE_HEIGHT,
    align: o.align,
    wrap: "word",
  });
  const h = node.height();
  node.destroy();
  return h;
}

/** Nesneleri sunucunun işlem listesine çevirir (core/content.py şemaları). */
export function toOps(objects: EditorObj[]): Record<string, unknown>[] {
  return objects.map((o) => {
    if (!isBox(o)) {
      return { type: o.kind, page: o.page, points: o.points, stroke: o.stroke, width: o.width, opacity: o.opacity };
    }
    const rect = [o.x, o.y, o.x + o.w, o.y + o.h];
    switch (o.kind) {
      case "text":
        return {
          type: "text",
          page: o.page,
          rect,
          text: o.text,
          font: o.font,
          bold: o.bold,
          size: o.size,
          color: o.color,
          align: o.align,
          line_height: LINE_HEIGHT,
          opacity: o.opacity,
          rotation: o.rotation,
        };
      case "image":
        return { type: "image", page: o.page, rect, asset: o.asset, opacity: o.opacity, rotation: o.rotation };
      case "highlight":
        return { type: "highlight", page: o.page, rect, color: o.color };
      case "rect":
      case "ellipse":
        return {
          type: o.kind,
          page: o.page,
          rect,
          stroke: o.stroke,
          fill: o.fill,
          width: o.width,
          opacity: o.opacity,
          rotation: o.rotation,
        };
      case "redact":
        return { type: "redact", page: o.page, rect, fill: o.color };
      case "whiteout":
        return { type: "whiteout", page: o.page, rect, color: o.color };
    }
  });
}

/** Araçla çizilen kutudan yeni nesne. */
export function createBox(tool: Tool, page: number, x: number, y: number, w: number, h: number): EditorObj | null {
  const base = { id: newId(), page, x, y, w, h, rotation: 0 };
  switch (tool) {
    case "text": {
      const t: TextObj = {
        ...base,
        kind: "text",
        text: "Yazı",
        font: "noto-sans",
        bold: false,
        size: 14,
        color: "#1a1a1a",
        align: "left",
        opacity: 1,
      };
      return { ...t, h: measureText(t) };
    }
    case "highlight":
      return { ...base, kind: "highlight", color: "#ffe066" };
    case "rect":
    case "ellipse":
      return { ...base, kind: tool, stroke: "#d00000", fill: null, width: 1.5, opacity: 1 };
    case "redact":
      return { ...base, kind: "redact", color: "#000000" };
    case "whiteout":
      return { ...base, kind: "whiteout", color: "#ffffff" };
    case "line":
    case "arrow":
      return {
        id: base.id,
        page,
        kind: tool,
        points: [x, y + h / 2, x + w, y + h / 2],
        stroke: "#d00000",
        width: 2,
        opacity: 1,
      };
    default:
      return null;
  }
}

export const TOOL_LABELS: Record<Tool, string> = {
  select: "Seç",
  text: "Yazı",
  image: "Resim",
  signature: "İmza",
  highlight: "Vurgu",
  rect: "Dikdörtgen",
  ellipse: "Elips",
  line: "Çizgi",
  arrow: "Ok",
  redact: "Karartma",
  whiteout: "Beyazla kapat",
};

export const KIND_LABELS: Record<EditorObj["kind"], string> = {
  text: "Yazı",
  image: "Resim",
  highlight: "Vurgu",
  rect: "Dikdörtgen",
  ellipse: "Elips",
  line: "Çizgi",
  arrow: "Ok",
  redact: "Karartma",
  whiteout: "Beyazla kapat",
};
