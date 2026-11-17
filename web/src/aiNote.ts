/** "Formülleri onar": ChatGPT gibi araçlardan yapıştırılan notlardaki \( … \) ve \[ … \]
 * formüllerini $ … $ / $$ … $$ biçimine çevirir, blok formüllerin boş satırlarını düzeltir. Kod
 * blokları ve satır içi kod atlanır. Önizleme bu ayraçları zaten tanır; düzeltme notun kendisi
 * içindir (indirilen .md Obsidian gibi başka programlarda da doğru görünsün). */

/** Düğmenin ipucu ve ekran okuyucu açıklaması. */
export const FORMULA_FIX_HINT =
  "ChatGPT gibi yapay zekâ araçlarından yapıştırılan notlardaki \\( … \\) ve \\[ … \\] formüllerini " +
  "$ … $ ve $$ … $$ biçimine çevirir, blok formüllerin boş satırlarını düzeltir. Not, Obsidian gibi " +
  "başka programlarda da doğru görünür. Ctrl+Z ile geri alınır.";

interface TextChunk {
  isCode: boolean;
  text: string;
}
const FENCE_RE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

function countBackslashesBefore(src: string, index: number): number {
  let count = 0;
  for (let i = index - 1; i >= 0 && src[i] === "\\"; i--) count++;
  return count;
}

function splitCodeFences(src: string): TextChunk[] {
  const parts: TextChunk[] = [];
  const lines = src.split(/(?<=\n)/);
  let buf: string[] = [];
  let fence: string | null = null;

  for (const line of lines) {
    const m = FENCE_RE.exec(line.replace(/\r?\n$/, ""));
    if (fence === null && m) {
      const marker = m[1];
      const info = m[2];
      // CommonMark: backtick kod bloğu bilgi satırı backtick içeremez.
      if (marker[0] === "`" && info.includes("`")) {
        buf.push(line);
        continue;
      }
      if (buf.length > 0) {
        parts.push({ isCode: false, text: buf.join("") });
        buf = [];
      }
      buf.push(line);
      fence = marker;
    } else if (fence !== null && m && m[1][0] === fence[0] && m[1].length >= fence.length && m[2].trim() === "") {
      buf.push(line);
      parts.push({ isCode: true, text: buf.join("") });
      buf = [];
      fence = null;
    } else {
      buf.push(line);
    }
  }
  if (buf.length > 0) parts.push({ isCode: fence !== null, text: buf.join("") });
  return parts;
}

function splitInlineCode(segment: string): TextChunk[] {
  const chunks: TextChunk[] = [];
  let plainStart = 0;
  let i = 0;

  while (i < segment.length) {
    if (segment[i] !== "`" || countBackslashesBefore(segment, i) % 2 === 1) {
      i++;
      continue;
    }
    let tickCount = 1;
    while (i + tickCount < segment.length && segment[i + tickCount] === "`") tickCount++;

    let j = i + tickCount;
    let closeStart = -1;
    while (j < segment.length) {
      if (segment[j] === "\n") {
        const rest = segment.slice(j + 1);
        if (/^[ \t]*\r?\n/.test(rest)) break;
        j++;
        continue;
      }
      if (segment[j] === "`") {
        let run = 1;
        while (j + run < segment.length && segment[j + run] === "`") run++;
        if (run === tickCount) {
          closeStart = j;
          break;
        }
        j += run;
        continue;
      }
      j++;
    }

    if (closeStart !== -1) {
      if (i > plainStart) chunks.push({ isCode: false, text: segment.slice(plainStart, i) });
      chunks.push({ isCode: true, text: segment.slice(i, closeStart + tickCount) });
      i = closeStart + tickCount;
      plainStart = i;
    } else {
      i += tickCount;
    }
  }

  if (plainStart < segment.length) chunks.push({ isCode: false, text: segment.slice(plainStart) });
  return chunks;
}

function findClosingDelimiter(src: string, start: number, close: string, stopOnBlankLine: boolean): number {
  let i = start;
  while (i <= src.length - close.length) {
    if (stopOnBlankLine && src[i] === "\n" && /^[ \t]*\r?\n/.test(src.slice(i + 1))) {
      return -1;
    }
    if (src.startsWith(close, i) && countBackslashesBefore(src, i) % 2 === 0) {
      return i;
    }
    i++;
  }
  return -1;
}

function convertLatexDelimiters(plain: string): { text: string; converted: number } {
  let out = "";
  let converted = 0;
  let i = 0;

  while (i < plain.length) {
    if (plain[i] === "\\" && countBackslashesBefore(plain, i) % 2 === 0) {
      const next = plain[i + 1];
      if (next === "[") {
        const close = findClosingDelimiter(plain, i + 2, "\\]", false);
        if (close !== -1) {
          const inner = plain.slice(i + 2, close).trim();
          if (inner.length > 0) {
            const lineStart = out.lastIndexOf("\n") + 1;
            const beforeOnLine = out.slice(lineStart);
            const bqMatch = /^([ \t]*(?:>[ \t]*)+)$/.exec(beforeOnLine);
            if (bqMatch) {
              const prefix = bqMatch[1];
              const body = inner
                .split(/\r?\n/)
                .map((l) => (/^[ \t]*>/.test(l) ? l : `${prefix}${l}`))
                .join("\n");
              out += `$$\n${body}\n${prefix}$$`;
            } else {
              const hadTextBefore = beforeOnLine.trim().length > 0;
              if (hadTextBefore) out = `${out.replace(/[ \t]+$/, "")}\n`;
              out += `$$\n${inner}\n$$`;
              const afterRest = plain.slice(close + 2);
              const sameLineAfter = afterRest.split(/\r?\n/, 1)[0];
              if (sameLineAfter.trim().length > 0) out += "\n";
            }
            converted++;
            i = close + 2;
            continue;
          }
        }
      } else if (next === "(") {
        const close = findClosingDelimiter(plain, i + 2, "\\)", true);
        if (close !== -1) {
          const inner = plain.slice(i + 2, close).trim();
          if (inner.length > 0) {
            out += `$${inner}$`;
            converted++;
            i = close + 2;
            continue;
          }
        }
      }
    }
    out += plain[i];
    i++;
  }

  return { text: out, converted };
}

function normalizeDisplayMathSpacing(src: string): string {
  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  let fence: string | null = null;
  let inMathBlock = false;
  let needBlankAfter = false;

  const ensureBlankBefore = () => {
    if (out.length > 0 && out[out.length - 1].trim() !== "") out.push("");
  };

  for (const line of lines) {
    if (inMathBlock) {
      const closeMatch = /^[ \t]*\$\$[ \t]*(\([^)\n]+\))?[ \t]*$/.exec(line);
      if (closeMatch) {
        out.push(closeMatch[1] ? `$$ ${closeMatch[1]}` : "$$");
        inMathBlock = false;
        needBlankAfter = true;
      } else {
        out.push(line);
      }
      continue;
    }

    const fenceMatch = FENCE_RE.exec(line);
    if (fence === null && fenceMatch) {
      const marker = fenceMatch[1];
      if (!(marker[0] === "`" && fenceMatch[2].includes("`"))) {
        if (needBlankAfter) {
          out.push("");
          needBlankAfter = false;
        }
        fence = marker;
        out.push(line);
        continue;
      }
    } else if (
      fence !== null &&
      fenceMatch &&
      fenceMatch[1][0] === fence[0] &&
      fenceMatch[1].length >= fence.length &&
      fenceMatch[2].trim() === ""
    ) {
      fence = null;
      out.push(line);
      continue;
    }

    if (fence !== null) {
      out.push(line);
      continue;
    }

    const singleLineMath = /^[ \t]*\$\$(.+?)\$\$([ \t]*(\([^)\n]+\)))?[ \t]*$/.exec(line);
    if (singleLineMath && !singleLineMath[1].includes("$$") && !singleLineMath[1].includes("`")) {
      const inner = singleLineMath[1].trim();
      if (inner.length > 0) {
        ensureBlankBefore();
        out.push("$$", inner, singleLineMath[3] ? `$$ ${singleLineMath[3]}` : "$$");
        needBlankAfter = true;
        continue;
      }
    }

    if (/^[ \t]*\$\$[ \t]*$/.test(line)) {
      needBlankAfter = false;
      ensureBlankBefore();
      out.push("$$");
      inMathBlock = true;
      continue;
    }

    if (needBlankAfter) {
      if (line.trim() !== "") out.push("");
      needBlankAfter = false;
    }
    out.push(line);
  }

  return out.join("\n");
}

/** AI çıktısındaki \(...\) ve \[...\] formüllerini kod bloklarını atlayarak $ / $$ biçimine çevirir. */
export function fixAiNote(src: string): { text: string; converted: number; changed: boolean } {
  let converted = 0;
  const convertedText = splitCodeFences(src)
    .map((part) => {
      if (part.isCode) return part.text;
      return splitInlineCode(part.text)
        .map((chunk) => {
          if (chunk.isCode) return chunk.text;
          const res = convertLatexDelimiters(chunk.text);
          converted += res.converted;
          return res.text;
        })
        .join("");
    })
    .join("");

  const text = normalizeDisplayMathSpacing(convertedText);
  return { text, converted, changed: text !== src };
}

/** Düğmeye basınca gösterilecek bildirim: ne yapıldığı ya da neden bir şey yapılmadığı. */
export function formulaFixMessage({ converted, changed }: { converted: number; changed: boolean }): {
  kind: "ok" | "info";
  text: string;
} {
  if (!changed) {
    return {
      kind: "info",
      text:
        "Onarılacak formül yok: notta \\( … \\) ya da \\[ … \\] biçiminde yazılmış formül bulunamadı. " +
        "$ … $ ve $$ … $$ ile yazılmış formüller zaten doğru.",
    };
  }
  return {
    kind: "ok",
    text:
      converted > 0
        ? `Formüller onarıldı: ${converted} formül $ … $ / $$ … $$ biçimine çevrildi. Geri almak için Ctrl+Z.`
        : "Blok formüllerin ($$ … $$) çevresindeki boş satırlar düzeltildi. Geri almak için Ctrl+Z.",
  };
}
