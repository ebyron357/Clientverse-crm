import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default class AppErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error) { console.error("ClientVerse route error", error); }
  render() {
    if (!this.state.hasError) return this.props.children;
    return <main className="flex min-h-screen items-center justify-center bg-[#f7fafc] p-6"><section className="cv-card max-w-md p-8 text-center"><span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 text-red-600"><AlertCircle className="h-6 w-6" /></span><h1 className="mt-5 font-display text-2xl font-extrabold text-[#0a1628]">This view needs a refresh</h1><p className="mt-2 text-sm leading-6 text-slate-500">ClientVerse could not render this screen. Your records have not been changed. Reload to return to your work.</p><Button onClick={() => window.location.reload()} className="mt-6 cv-action-primary"><RefreshCw className="mr-2 h-4 w-4" />Reload ClientVerse</Button></section></main>;
  }
}
