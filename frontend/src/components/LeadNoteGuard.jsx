import { useEffect } from "react";
import { useBlocker } from "react-router-dom";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function LeadNoteGuard({ dirty, saving, noteRef }) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    (dirty || saving) && (currentLocation.pathname !== nextLocation.pathname ||
      new URLSearchParams(currentLocation.search).get("lead") !== new URLSearchParams(nextLocation.search).get("lead")));

  useEffect(() => {
    if (!dirty && !saving) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, saving]);

  useEffect(() => {
    // A confirmed save does not replay a navigation requested while it was in flight.
    if (!dirty && !saving && blocker.state === "blocked") blocker.reset();
  }, [dirty, saving, blocker]);

  return (
    <AlertDialog open={blocker.state === "blocked"} onOpenChange={(open) => {
      if (!open && blocker.state === "blocked") blocker.reset();
    }}>
      <AlertDialogContent className="max-w-[calc(100%-2rem)] rounded-lg sm:max-w-md"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          noteRef.current?.focus();
        }}>
        <AlertDialogHeader>
          <AlertDialogTitle>{saving ? "Update still saving" : "Discard your unsaved note?"}</AlertDialogTitle>
          <AlertDialogDescription>
            {saving ? "Please wait for the update to finish. Leaving now could make its outcome unclear."
              : "This note has not been saved. Keep editing to save it with a status update, or discard it to continue. This does not change the lead’s saved status."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="min-h-11" data-testid="lead-note-keep">{saving ? "Stay on lead" : "Keep editing"}</AlertDialogCancel>
          {!saving && <AlertDialogAction className="min-h-11" data-testid="lead-note-discard" onClick={(event) => {
            event.preventDefault();
            blocker.proceed();
          }}>Discard note</AlertDialogAction>}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
