import React from "react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import SignalsTable from "../components/SignalsTable";

export default function Signals() {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Signals</h1>
          <p className="text-muted-foreground">View and manage harvested signals.</p>
        </div>
        <Link to="/signals/new">
          <Button>Create Signal</Button>
        </Link>
      </div>

      <SignalsTable />
    </div>
  );
}
