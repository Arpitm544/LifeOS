import Image from "next/image";

export function Orbit({ variant = "today", className = "" }: { variant?: "today" | "voice" | "profile"; className?: string }) {
  const size = variant === "voice" ? 240 : variant === "profile" ? 190 : 286;
  return <div className={`orbit ${className}`} aria-hidden="true"><Image src={`/images/orbit-${variant}.svg`} alt="" width={size} height={size} priority={variant === "today"} /></div>;
}
