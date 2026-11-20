/** Toolia kelebek simgesi (üst çubuk ve karşılama ekranı). Tek kaynak: paket/simge.py
 * (tests/test_simge.py buradaki çokgenlerin oradakiyle aynı olduğunu denetler). */
export default function BrandMark({ size = 30, className = "brand-mark" }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 1024 1024" aria-hidden="true">
      <rect x="43" y="43" width="938" height="938" rx="173" fill="#fff" stroke="#E3E6EC" strokeWidth="6" />
      <polygon points="161.6,222.5 363.3,277.5 495.6,415.1 495.6,495 261.1,495 207.4,438.6" fill="#2E5BE6" />
      <polygon points="862.4,222.5 660.7,277.5 528.4,415.1 528.4,495 762.9,495 816.6,438.6" fill="#7C4DDB" />
      <polygon points="245.4,598.5 313.5,527.7 495.6,527.7 495.6,633.8 383,806.8 271.6,700.6" fill="#22A06B" />
      <polygon points="778.6,598.5 710.5,527.7 528.4,527.7 528.4,633.8 641,806.8 752.4,700.6" fill="#F5A524" />
    </svg>
  );
}
