import { Field, PanelSection } from "@decky/ui";
import { useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { saveLsfg } from "../backend";
import { SelectEdit, ToggleRow } from "../components/widgets";
import type { Config, LsfgConfig } from "../types";

const MULTIPLIERS = [
  { data: "2", label: "2x" },
  { data: "3", label: "3x" },
  { data: "4", label: "4x" },
];

const FLOW_SCALES = [
  { data: "1.0", label: "1.0 — best motion detail" },
  { data: "0.75", label: "0.75 — balanced" },
  { data: "0.5", label: "0.5 — faster" },
  { data: "0.25", label: "0.25 — fastest" },
];

const PRESENT_MODES = [
  { data: "", label: "Automatic" },
  { data: "fifo", label: "FIFO / VSync" },
  { data: "mailbox", label: "Mailbox" },
  { data: "immediate", label: "Immediate" },
];

export function Lsfg({ config, setConfig }: {
  config: Config;
  setConfig: Dispatch<SetStateAction<Config | null>>;
}) {
  const revision = useRef(0);
  const saveChain = useRef<Promise<void>>(Promise.resolve());
  const [message, setMessage] = useState("");
  const state = config.lsfg;

  if (!state?.supported) {
    return (
      <PanelSection title="LSFG-VK frame generation">
        <Field label="System layer unavailable" description={state?.reason || "LSFG-VK is not installed in this image."} />
      </PanelSection>
    );
  }

  const settings = state.config;
  const layerStatus = [
    state.layers.native ? "native ARM" : "",
    state.layers.x64 ? "x64/Wine" : "",
  ].filter(Boolean).join(" + ");

  const apply = (patch: Partial<LsfgConfig>) => {
    const next = { ...settings, ...patch };
    const request = ++revision.current;
    setMessage("");
    setConfig((current) => current?.lsfg
      ? { ...current, lsfg: { ...current.lsfg, config: next } }
      : current);
    saveChain.current = saveChain.current.catch(() => {}).then(async () => {
      try {
        const saved = await saveLsfg(next);
        if (request === revision.current) {
          setConfig((current) => (current ? { ...current, lsfg: saved } : current));
          setMessage("Saved — applies after Steam/GamepadUI is relaunched.");
        }
      } catch (error) {
        if (request === revision.current) setMessage(String(error));
      }
    });
  };

  return (
    <>
      <PanelSection title="LSFG-VK frame generation">
        <Field
          label="Batocera system layer"
          description={`${layerStatus || "detected"}; no separate LSFG runtime is downloaded by this plugin.`}
        />
        <Field
          label={state.dllDetected ? "Lossless.dll detected" : "Lossless.dll missing"}
          description={state.dllPath}
        />
        <ToggleRow
          label="Enable for Steam games"
          description="Injects Batocera's LSFG-VK Vulkan layer into Steam-launched Vulkan/DXVK games on the next Steam launch."
          value={settings.enabled}
          disabled={!state.ready}
          onChange={(enabled) => apply({ enabled })}
        />
        {!state.dllDetected ? (
          <Field label="Required file" description="Copy Lossless.dll from a purchased Lossless Scaling installation to the path shown above." />
        ) : null}
      </PanelSection>

      <PanelSection title="Frame generation">
        <Field label="Frame multiplier" description="2x has the lowest GPU cost; 3x/4x synthesize more frames and require more headroom." />
        <SelectEdit label="Multiplier" value={settings.multiplier} options={MULTIPLIERS} onChange={(multiplier) => apply({ multiplier })} />
        <Field label="Optical-flow resolution" description="Lower values reduce motion-estimation cost at the expense of generated-frame detail." />
        <SelectEdit label="Flow scale" value={settings.flowScale} options={FLOW_SCALES} onChange={(flowScale) => apply({ flowScale })} />
        <ToggleRow
          label="Performance mode"
          description="Uses the lighter LSFG model. Recommended on SM8550/SM8750 when games are GPU-bound."
          value={settings.performanceMode}
          onChange={(performanceMode) => apply({ performanceMode })}
        />
        <ToggleRow
          label="HDR mode"
          description="Enable only when both the game and display session are using HDR."
          value={settings.hdrMode}
          onChange={(hdrMode) => apply({ hdrMode })}
        />
        <Field label="Present mode" description="Automatic is safest. FIFO favors tear-free output; Mailbox/Immediate may reduce latency but can stutter or tear." />
        <SelectEdit label="Vulkan present mode" value={settings.presentMode} options={PRESENT_MODES} onChange={(presentMode) => apply({ presentMode })} />
      </PanelSection>

      <PanelSection title="Activation">
        <Field label="Restart required" description={message || "Changes apply the next time Steam/GamepadUI starts; currently running games keep the old environment."} />
        {state.legacyPluginDetected || state.legacyConfigDetected || state.legacyLaunchScriptDetected ? (
          <Field
            label="Legacy LSFG setup detected"
            description="The old Decky plugin/wrapper is retained for rollback. Remove ~/lsfg from per-game Steam launch options before enabling Batocera's global layer to avoid double injection."
          />
        ) : null}
        <Field label="Upstream" description="System layer: PancakeTAS/lsfg-vk. UI integration derived from Decky LSFG-VK concepts." />
      </PanelSection>
    </>
  );
}
