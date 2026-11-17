import type { LucideIcon, LucideProps } from "lucide-react";

interface Props extends Omit<LucideProps, "ref"> {
  icon: LucideIcon;
  /** Anlam taşıyan ikon için metin. Yoksa ikon süstür, ekran okuyucudan gizlenir. */
  label?: string;
}

/** Bütün arayüzde tek ikon biçimi: 18px, 2px çizgi, `currentColor`. Yalnız ikonlu düğmede
 * adı düğmeye ver (`aria-label`), ikona değil. */
export default function Icon({ icon: Glyph, size = 18, strokeWidth = 2, label, className, ...rest }: Props) {
  return (
    <Glyph
      size={size}
      strokeWidth={strokeWidth}
      className={className ? `icon ${className}` : "icon"}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      {...rest}
    />
  );
}
