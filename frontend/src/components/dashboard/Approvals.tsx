import { ShieldCheck } from "lucide-react";

interface ApprovalsProps {
  onOpen: () => void;
}

export default function Approvals({
  onOpen,
}: ApprovalsProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Privacy &amp; approvals</h2>
        <ShieldCheck size={19} />
      </div>

      <div className="empty-state">
        <strong>External execution is disabled</strong>
        <p>
          Manual approval records do not grant permissions
          or authorize external actions.
        </p>
      </div>

      <button className="secondary-button" onClick={onOpen}>
        View approval records
      </button>
    </section>
  );
}
