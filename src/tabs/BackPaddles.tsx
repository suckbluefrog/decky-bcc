import { Field, PanelSection } from "@decky/ui";
import { useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import { saveBackPaddles } from "../backend";
import { SelectEdit } from "../components/widgets";
import type { BackPaddleBindings, Config } from "../types";

export function BackPaddles({ config, setConfig }: {
  config: Config;
  setConfig: Dispatch<SetStateAction<Config | null>>;
}) {
  const revision = useRef(0);
  const saveChain = useRef<Promise<void>>(Promise.resolve());
  const bp = config.backPaddles;
  if (!bp?.supported) {
    return <PanelSection title="Back paddles"><Field label="Unavailable" description={bp?.reason || "GPIO paddles were not detected."} /></PanelSection>;
  }

  const bindings = bp.bindings;
  const slots = bp.slots || [];
  const actions = bp.actions || [];

  const apply = (next: BackPaddleBindings) => {
    const request = ++revision.current;
    setConfig((current) => (current && current.backPaddles ? { ...current, backPaddles: { ...current.backPaddles, bindings: next } } : current));
    saveChain.current = saveChain.current.catch(() => {}).then(async () => {
      try {
        const state = await saveBackPaddles(next);
        if (request === revision.current) {
          setConfig((current) => (current ? { ...current, backPaddles: state } : current));
        }
      } catch (error) {
        console.error(error);
      }
    });
  };

  const update = (slot: keyof BackPaddleBindings, action: string) => {
    apply({ ...bindings, [slot]: action });
  };

  return (
    <>
      <PanelSection title="Back paddles (M1 / M2)">
        <Field
          label="GPIO + combos"
          children="Tap actions fire on release. Combos fire while M1/M2 is held and the second button is pressed."
        />
      </PanelSection>
      <PanelSection title="Bindings">
        {bp.warning ? <Field label="Warning" description={bp.warning} /> : null}
        {slots.map((slot) => (
          <SelectEdit
            key={slot.data}
            label={slot.label}
            value={bindings[slot.data as keyof BackPaddleBindings] || "none"}
            options={actions}
            onChange={(value) => update(slot.data as keyof BackPaddleBindings, value)}
          />
        ))}
      </PanelSection>
    </>
  );
}
