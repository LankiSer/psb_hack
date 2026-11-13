import Image from "next/image";

export default function Brand() {
  return <span className="psb-brand"><Image src="/brand/psb.svg" alt="ПСБ" width={84} height={32} priority/><span>Банк Docs</span></span>;
}
