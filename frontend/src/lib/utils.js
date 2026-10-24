import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"
import { toast } from "sonner";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Copy text and say truthfully whether it worked. A browser can refuse the clipboard
 * (permissions, Safari after an await, an insecure page); "copied" must not be shown
 * then, above all for something shown only once, such as a key or a portal link.
 */
export async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${label} copied`);
    return true;
  } catch {
    toast.error(`Couldn't copy the ${label.toLowerCase()}`, { description: "Select the text and copy it by hand." });
    return false;
  }
}
