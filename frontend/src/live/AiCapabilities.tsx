import { ACTIVE_AGENTS, AGENT_LABEL, AGENT_PRODUCT_BLURB, AGENT_PRODUCT_NAME } from '../lib/format';
import { capabilityStatus } from '../lib/situation';
import { useAgentStore, useSimStore } from '../store';

/**
 * The three AI capabilities as a customer sees them (R11 §10, §11). Human explanation
 * first; the algorithm name stays as a small secondary tag. Status words come from the
 * real coordinator winner and live emergency state.
 */
export function AiCapabilities() {
  const state = useSimStore((s) => s.state);
  const coordination = useAgentStore((s) => s.coordination);

  return (
    <section className="ai-caps" aria-label="AI control">
      <h2 className="panel-kicker">AI control</h2>
      <ul className="ai-cap-list">
        {ACTIVE_AGENTS.map((agent) => {
          const st = capabilityStatus(agent, state, coordination);
          return (
            <li className={st.active ? 'ai-cap active' : 'ai-cap'} key={agent}>
              <span className={st.active ? 'ai-cap-dot on' : 'ai-cap-dot'} aria-hidden="true" />
              <div className="ai-cap-text">
                <span className="ai-cap-name">
                  {AGENT_PRODUCT_NAME[agent]}
                  <span className="ai-cap-algo">{AGENT_LABEL[agent]}</span>
                </span>
                <span className="ai-cap-blurb">{AGENT_PRODUCT_BLURB[agent]}</span>
              </div>
              <span className="ai-cap-status">{st.label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
