import type Konva from "konva";
import type { KonvaEventObject } from "konva/lib/Node";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import { useEffect, useRef, useState } from "react";
import { Arrow, Circle, Ellipse, Group, Image as KImage, Layer, Line, Rect, Stage, Text, Transformer } from "react-konva";
import { api } from "../api";
import {
  canRotate,
  createBox,
  FONT_CSS,
  isBox,
  LINE_HEIGHT,
  measureText,
  type BoxObj,
  type EditorObj,
  type LineObj,
  type Tool,
} from "./model";

interface Props {
  doc: PDFDocumentProxy;
  pageIndex: number;
  scale: number;
  objects: EditorObj[];
  selectedId: string | null;
  tool: Tool;
  onSelect: (id: string | null) => void;
  onChange: (obj: EditorObj) => void;
  onCreate: (obj: EditorObj) => void;
  onEditText: (id: string) => void;
  onPageSize?: (w: number, h: number) => void;
}

// Tıklayıp sürüklemeden bırakınca oluşacak varsayılan boyut (nokta).
const DEFAULT_SIZE: Partial<Record<Tool, [number, number]>> = {
  text: [200, 20],
  highlight: [160, 16],
  rect: [120, 70],
  ellipse: [120, 70],
  redact: [140, 22],
  whiteout: [140, 22],
  line: [140, 0],
  arrow: [140, 0],
};

const MAX_CANVAS_SIDE = 4096;
const MAX_CANVAS_PIXELS = 16_777_216;

const images = new Map<string, HTMLImageElement>();

function useAsset(id: string): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(() => {
    const cached = images.get(id);
    return cached?.complete ? cached : null;
  });
  useEffect(() => {
    if (!id) return;
    let el = images.get(id);
    if (!el) {
      el = new window.Image();
      el.src = api.rawUrl(id);
      images.set(id, el);
    }
    if (el.complete && el.naturalWidth) return setImg(el);
    const done = () => setImg(el!);
    el.addEventListener("load", done);
    return () => el!.removeEventListener("load", done);
  }, [id]);
  return img;
}

/** pdf.js ile çizilmiş sayfa + üstünde düzenlenebilir Konva katmanı. */
export default function PageCanvas(props: Props) {
  const { doc, pageIndex, scale, objects, selectedId, tool } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const trRef = useRef<Konva.Transformer>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [draft, setDraft] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  // Sayfayı çiz. Görünüm alanı pdf.js'te de döndürme + CropBox'ı içerir (sunucuyla aynı uzay).
  useEffect(() => {
    let task: RenderTask | null = null;
    let alive = true;
    let pageObj: { cleanup?: () => void } | null = null;
    const canvas = canvasRef.current;
    void doc.getPage(pageIndex + 1).then((page) => {
      if (!alive) return;
      pageObj = page;
      const base = page.getViewport({ scale: 1 });
      setSize({ w: base.width, h: base.height });
      props.onPageSize?.(base.width, base.height);
      const ratio = window.devicePixelRatio || 1;
      let renderScale = scale * ratio;

      // A0 OOM Koruması: MAX_CANVAS_SIDE ve MAX_CANVAS_PIXELS
      if (base.width * renderScale > MAX_CANVAS_SIDE) {
        renderScale = MAX_CANVAS_SIDE / base.width;
      }
      if (base.height * renderScale > MAX_CANVAS_SIDE) {
        renderScale = MAX_CANVAS_SIDE / base.height;
      }
      const totalPixels = base.width * renderScale * (base.height * renderScale);
      if (totalPixels > MAX_CANVAS_PIXELS) {
        const factor = Math.sqrt(MAX_CANVAS_PIXELS / totalPixels);
        renderScale *= factor;
      }

      const viewport = page.getViewport({ scale: renderScale });
      if (!canvas) return;
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      task = page.render({ canvas, viewport });
      task.promise.catch(() => undefined);
    });
    return () => {
      alive = false;
      task?.cancel();
      try {
        pageObj?.cleanup?.();
      } catch {
        /* yoksay */
      }
      if (canvas) {
        canvas.width = 0;
        canvas.height = 0;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, pageIndex, scale]);

  // Seçili kutuya dönüştürücü bağla.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    const sel = objects.find((o) => o.id === selectedId);
    const node = sel && isBox(sel) && tool === "select" ? stage.findOne(`#${sel.id}`) : null;
    tr.nodes(node ? [node] : []);
    if (sel && isBox(sel)) {
      tr.rotateEnabled(canRotate(sel));
      tr.keepRatio(sel.kind === "image");
      tr.enabledAnchors(
        sel.kind === "text"
          ? ["middle-left", "middle-right"]
          : sel.kind === "image"
            ? ["top-left", "top-right", "bottom-left", "bottom-right"]
            : ["top-left", "top-center", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-center", "bottom-right"],
      );
    }
    tr.getLayer()?.batchDraw();
  }, [objects, selectedId, tool]);

  const pointer = (): { x: number; y: number } | null => {
    const p = stageRef.current?.getPointerPosition();
    return p ? { x: p.x / scale, y: p.y / scale } : null;
  };

  const onDown = (e: KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (tool === "select") {
      if (e.target === e.target.getStage()) props.onSelect(null);
      return;
    }
    if (tool === "image" || tool === "signature") return;
    const p = pointer();
    if (p) setDraft({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
  };

  const onMove = () => {
    if (!draft) return;
    const p = pointer();
    if (p) setDraft({ ...draft, x1: p.x, y1: p.y });
  };

  const onUp = () => {
    if (!draft) return;
    setDraft(null);
    const isLine = tool === "line" || tool === "arrow";
    const { x0, y0 } = draft;
    let { x1, y1 } = draft;
    const dragged = Math.hypot(x1 - x0, y1 - y0) > 4;
    if (!dragged) {
      const [w, h] = DEFAULT_SIZE[tool] ?? [100, 40];
      x1 = x0 + w;
      y1 = y0 + h;
    }
    if (isLine) {
      const obj = createBox(tool, pageIndex, 0, 0, 0, 0) as LineObj;
      props.onCreate({ ...obj, points: [x0, y0, x1, dragged ? y1 : y0] });
      return;
    }
    const x = Math.min(x0, x1);
    const y = Math.min(y0, y1);
    const obj = createBox(tool, pageIndex, x, y, Math.max(8, Math.abs(x1 - x0)), Math.max(8, Math.abs(y1 - y0)));
    if (obj) props.onCreate(obj);
  };

  if (!size) {
    return (
      <div className="editor-page loading">
        <canvas ref={canvasRef} />
      </div>
    );
  }

  const pageObjects = objects.filter((o) => o.page === pageIndex);
  return (
    <div
      className={`editor-page tool-${tool}`}
      style={{ width: size.w * scale, height: size.h * scale }}
    >
      <canvas ref={canvasRef} style={{ width: size.w * scale, height: size.h * scale }} />
      <Stage
        ref={stageRef}
        width={size.w * scale}
        height={size.h * scale}
        className="editor-stage"
        onMouseDown={onDown}
        onTouchStart={onDown}
        onMouseMove={onMove}
        onTouchMove={onMove}
        onMouseUp={onUp}
        onTouchEnd={onUp}
      >
        <Layer scaleX={scale} scaleY={scale}>
          {pageObjects.map((o) =>
            isBox(o) ? (
              <BoxNode
                key={o.id}
                obj={o}
                scale={scale}
                interactive={tool === "select"}
                onSelect={() => props.onSelect(o.id)}
                onChange={props.onChange}
                onDblClick={() => o.kind === "text" && props.onEditText(o.id)}
              />
            ) : (
              <LineNode
                key={o.id}
                obj={o}
                scale={scale}
                selected={o.id === selectedId}
                interactive={tool === "select"}
                onSelect={() => props.onSelect(o.id)}
                onChange={props.onChange}
              />
            ),
          )}
          {draft && <Draft tool={tool} {...draft} scale={scale} />}
        </Layer>
        <Layer>
          <Transformer
            ref={trRef}
            rotationSnaps={[0, 90, 180, 270]}
            borderStroke="#c2410c"
            anchorStroke="#c2410c"
            anchorSize={9}
            boundBoxFunc={(oldBox, box) => (Math.abs(box.width) < 6 || Math.abs(box.height) < 6 ? oldBox : box)}
          />
        </Layer>
      </Stage>
    </div>
  );
}

function Draft({ tool, x0, y0, x1, y1, scale }: { tool: Tool; x0: number; y0: number; x1: number; y1: number; scale: number }) {
  const common = { stroke: "#c2410c", strokeWidth: 1 / scale, dash: [4 / scale, 3 / scale], listening: false };
  if (tool === "line" || tool === "arrow") return <Line points={[x0, y0, x1, y1]} {...common} />;
  return <Rect x={Math.min(x0, x1)} y={Math.min(y0, y1)} width={Math.abs(x1 - x0)} height={Math.abs(y1 - y0)} {...common} />;
}

interface BoxProps {
  obj: BoxObj;
  scale: number;
  interactive: boolean;
  onSelect: () => void;
  onChange: (o: EditorObj) => void;
  onDblClick: () => void;
}

function BoxNode({ obj, scale, interactive, onSelect, onChange, onDblClick }: BoxProps) {
  const { w, h } = obj;
  const img = useAsset(obj.kind === "image" ? obj.asset : "");

  const onDragEnd = (e: KonvaEventObject<DragEvent>) => {
    const n = e.target;
    onChange({ ...obj, x: n.x() - w / 2, y: n.y() - h / 2 });
  };

  const onTransformEnd = (e: KonvaEventObject<Event>) => {
    const n = e.target;
    const nw = Math.max(6, w * Math.abs(n.scaleX()));
    let nh = Math.max(6, h * Math.abs(n.scaleY()));
    n.scale({ x: 1, y: 1 });
    const cx = n.x();
    const cy = n.y();
    const rotation = Math.round(n.rotation() * 10) / 10;
    if (obj.kind === "text") nh = measureText({ ...obj, w: nw });
    onChange({ ...obj, x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh, rotation: canRotate(obj) ? rotation : 0 });
  };

  let body;
  switch (obj.kind) {
    case "text":
      body = (
        <Text
          x={-w / 2}
          y={-h / 2}
          width={w}
          text={obj.text}
          fontFamily={FONT_CSS[obj.font]}
          fontStyle={obj.bold ? "bold" : "normal"}
          fontSize={obj.size}
          fill={obj.color}
          align={obj.align}
          lineHeight={LINE_HEIGHT}
          opacity={obj.opacity}
          wrap="word"
        />
      );
      break;
    case "image":
      body = img ? (
        <KImage image={img} x={-w / 2} y={-h / 2} width={w} height={h} opacity={obj.opacity} />
      ) : (
        <Rect x={-w / 2} y={-h / 2} width={w} height={h} stroke="#999" dash={[4, 3]} strokeWidth={1 / scale} />
      );
      break;
    case "highlight":
      body = (
        <Rect x={-w / 2} y={-h / 2} width={w} height={h} fill={obj.color} opacity={0.5} globalCompositeOperation="multiply" />
      );
      break;
    case "rect":
    case "ellipse": {
      const style = {
        stroke: obj.stroke ?? undefined,
        strokeWidth: obj.stroke ? obj.width : 0,
        fill: obj.fill ?? undefined,
        opacity: obj.opacity,
        // Dolgusuz şekil içinden de tutulabilsin.
        hitStrokeWidth: Math.max(obj.width, 8 / scale),
        fillEnabled: !!obj.fill,
      };
      body =
        obj.kind === "rect" ? (
          <Rect x={-w / 2} y={-h / 2} width={w} height={h} {...style} />
        ) : (
          <Ellipse x={0} y={0} radiusX={w / 2} radiusY={h / 2} {...style} />
        );
      if (!obj.fill) {
        body = (
          <>
            <Rect x={-w / 2} y={-h / 2} width={w} height={h} fill="transparent" />
            {body}
          </>
        );
      }
      break;
    }
    case "redact":
      body = (
        <Rect
          x={-w / 2}
          y={-h / 2}
          width={w}
          height={h}
          fill={obj.color}
          opacity={0.85}
          stroke="#dc2626"
          strokeWidth={1.5 / scale}
          dash={[5 / scale, 3 / scale]}
        />
      );
      break;
    case "whiteout":
      body = (
        <Rect
          x={-w / 2}
          y={-h / 2}
          width={w}
          height={h}
          fill={obj.color}
          stroke="#9ca3af"
          strokeWidth={1 / scale}
          dash={[4 / scale, 3 / scale]}
        />
      );
      break;
  }

  return (
    <Group
      id={obj.id}
      x={obj.x + w / 2}
      y={obj.y + h / 2}
      rotation={obj.rotation}
      draggable={interactive}
      listening={interactive}
      onMouseDown={onSelect}
      onTouchStart={onSelect}
      onDragStart={onSelect}
      onDragEnd={onDragEnd}
      onTransformEnd={onTransformEnd}
      onDblClick={onDblClick}
      onDblTap={onDblClick}
    >
      {body}
    </Group>
  );
}

interface LineProps {
  obj: LineObj;
  scale: number;
  selected: boolean;
  interactive: boolean;
  onSelect: () => void;
  onChange: (o: EditorObj) => void;
}

function LineNode({ obj, scale, selected, interactive, onSelect, onChange }: LineProps) {
  const [localPoints, setLocalPoints] = useState<[number, number, number, number] | null>(null);
  const currentPoints = localPoints ?? obj.points;
  const [x1, y1, x2, y2] = currentPoints;
  const common = {
    points: currentPoints,
    stroke: obj.stroke,
    strokeWidth: obj.width,
    opacity: obj.opacity,
    hitStrokeWidth: Math.max(obj.width, 10 / scale),
    lineCap: "round" as const,
    draggable: interactive,
    listening: interactive,
    onMouseDown: onSelect,
    onTouchStart: onSelect,
    onDragEnd: (e: KonvaEventObject<DragEvent>) => {
      const n = e.target;
      const dx = n.x();
      const dy = n.y();
      n.position({ x: 0, y: 0 });
      setLocalPoints(null);
      onChange({ ...obj, points: [x1 + dx, y1 + dy, x2 + dx, y2 + dy] });
    },
  };
  const head = Math.max(8, obj.width * 4);
  const handle = (i: 0 | 1) => (
    <Circle
      key={i}
      x={i ? x2 : x1}
      y={i ? y2 : y1}
      radius={5 / scale}
      fill="#fff"
      stroke="#c2410c"
      strokeWidth={1.5 / scale}
      draggable
      onDragMove={(e) => {
        const p = e.target.position();
        setLocalPoints(i ? [x1, y1, p.x, p.y] : [p.x, p.y, x2, y2]);
      }}
      onDragEnd={(e) => {
        const p = e.target.position();
        const next: [number, number, number, number] = i ? [x1, y1, p.x, p.y] : [p.x, p.y, x2, y2];
        setLocalPoints(null);
        onChange({ ...obj, points: next });
      }}
    />
  );
  return (
    <>
      {obj.kind === "arrow" ? (
        <Arrow {...common} fill={obj.stroke} pointerLength={head} pointerWidth={head} />
      ) : (
        <Line {...common} />
      )}
      {selected && interactive && [handle(0), handle(1)]}
    </>
  );
}
