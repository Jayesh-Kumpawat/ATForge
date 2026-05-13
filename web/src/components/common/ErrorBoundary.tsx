"use client";

import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error("ErrorBoundary caught:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen gap-4 p-6">
          <h1 className="text-xl font-semibold">Something went wrong.</h1>
          <p className="text-sm text-muted-foreground">{this.state.error?.message}</p>
          <Button onClick={() => this.setState({ hasError: false, error: null })}>Reload</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
