import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Extract trailing number from person ID for friendly display.
 *  e.g. "cam0_person_162" → "#162" */
export function formatPersonId(personId: string): string {
  const match = personId.match(/(\d+)$/);
  return match ? `#${match[1]}` : personId;
}
