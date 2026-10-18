/* Changing your own password: the Settings dialog, and the screen a temporary password
   opens onto. Both use one form, which keeps this session signed in and ends the rest. */
import { useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff, KeyRound, LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, formatErr, setStoredToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const MIN_LENGTH = 8;

function PasswordField({ id, label, value, onChange, autoComplete, shown, testid }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={shown ? "text" : "password"} value={value} autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)} data-testid={testid} />
    </div>
  );
}

export function ChangePasswordForm({ temporary = false, onDone }) {
  const { setUser } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (next.length < MIN_LENGTH) { setError(`Choose a password with at least ${MIN_LENGTH} characters.`); return; }
    if (next !== confirm) { setError("The two new passwords don't match."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/auth/change-password", { current_password: current, new_password: next });
      setStoredToken(data.token);
      setUser(data.user);
      toast.success("Password changed", { description: "You're still signed in here. Any other device has been signed out." });
      if (onDone) onDone();
    } catch (requestError) {
      setError(formatErr(requestError.response?.data?.detail) || "Your password could not be changed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid gap-4" data-testid="change-password-form">
      <PasswordField id="current-password" label={temporary ? "Temporary password" : "Current password"} value={current}
        onChange={setCurrent} autoComplete="current-password" shown={shown} testid="current-password-input" />
      <PasswordField id="new-password" label="New password" value={next} onChange={setNext}
        autoComplete="new-password" shown={shown} testid="new-password-input" />
      <PasswordField id="confirm-password" label="New password again" value={confirm} onChange={setConfirm}
        autoComplete="new-password" shown={shown} testid="confirm-password-input" />
      <button type="button" onClick={() => setShown((value) => !value)} className="flex w-fit items-center gap-1.5 text-xs font-semibold text-[#0a6177]">
        {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}{shown ? "Hide passwords" : "Show passwords"}
      </button>
      <p className="text-xs leading-5 text-slate-500">At least {MIN_LENGTH} characters. A short sentence you'll remember works well.</p>
      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert" data-testid="change-password-error">{error}</div>}
      <Button type="submit" className="cv-action-primary" disabled={busy || !current || !next || !confirm} data-testid="change-password-submit">
        {busy ? "Saving…" : temporary ? "Save my password" : "Change password"}
      </Button>
    </form>
  );
}

export function ChangePasswordDialog({ open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="change-password-dialog">
        <DialogHeader>
          <DialogTitle>Change your password</DialogTitle>
          <DialogDescription>You'll stay signed in here. Any other phone or computer signed in to your account is signed out.</DialogDescription>
        </DialogHeader>
        {open && <ChangePasswordForm onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

// Shown instead of the app after signing in with a temporary password: until it is
// replaced the server answers nothing else.
export function ChooseOwnPassword() {
  const { user, logout } = useAuth();
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f7fafc] p-4" data-testid="choose-own-password">
      <div className="cv-card w-full max-w-md p-6 sm:p-7">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-50 text-[#0a6177]"><KeyRound className="h-5 w-5" /></span>
        <h1 className="mt-4 font-display text-2xl font-bold text-[#0a1628]">Choose your own password</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {user?.name ? `Welcome, ${user.name.split(" ")[0]}. ` : ""}You signed in with a temporary password. Type it once more, then choose a password only you know.
        </p>
        <div className="mt-5"><ChangePasswordForm temporary /></div>
        <button type="button" onClick={logout} className="mt-5 flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700">
          <LogOut className="h-3.5 w-3.5" />Sign out
        </button>
      </div>
    </div>
  );
}
