import type { CSSProperties } from "react";
const paths: Record<string, string> = {
 settings:"M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
 menu:"M4 6h16 M4 12h16 M4 18h16",
 doc:"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h6",
 folder:"M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
 search:"M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
 plus:"M12 5v14 M5 12h14", upload:"M12 16V3 M7 8l5-5 5 5 M4 16v5h16v-5",
 arrow:"M19 12H5 M12 5l-7 7 7 7", download:"M12 3v13 M7 11l5 5 5-5 M4 17v4h16v-4",
 spark:"m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7z",
 close:"M6 6l12 12 M18 6 6 18", trash:"M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7",
 grid:"M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
 list:"M8 6h13 M8 12h13 M8 18h13 M3 6h1 M3 12h1 M3 18h1",
 check:"M5 12l4 4L19 6", exit:"M9 21H4V3h5 M13 8l5 4-5 4 M8 12h13", send:"m22 2-7 20-4-9-9-4z M22 2 11 13",
 clock:"M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0"
};
export default function Icon({name,size=20,style}:{name:string;size?:number;style?:CSSProperties}) {return <svg aria-hidden="true" width={size} height={size} style={style} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name] || paths.doc}/></svg>}
