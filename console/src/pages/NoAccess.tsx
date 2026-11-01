import { Link } from "react-router";

export function NoAccess() {
  return (
    <section className="page narrow">
      <h1>You don't have access to this</h1>
      <p>Ask an Admin if you need it. Your dashboards are still where you left them.</p>
      <Link to="/">Back to your dashboard</Link>
    </section>
  );
}
