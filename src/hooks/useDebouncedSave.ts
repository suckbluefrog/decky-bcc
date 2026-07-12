import { useEffect, useRef } from "react";
import type { MutableRefObject, Dispatch, SetStateAction } from "react";
import type { Config } from "../types";

interface DebouncedSaveOptions {
  config: Config | null;
  field: "power" | "tweaks";
  snapshot: MutableRefObject<string>;
  save: (value: any) => Promise<Config>;
  setConfig: Dispatch<SetStateAction<Config | null>>;
  onError?: (error: unknown) => void;
  delay?: number;
}

export function useDebouncedSave(options: DebouncedSaveOptions) {
  const { config, field, snapshot, save, setConfig, onError, delay = 900 } = options;
  const value = config ? (config as any)[field] : undefined;
  const saveChain = useRef<Promise<void>>(Promise.resolve());
  const revision = useRef(0);
  useEffect(() => {
    if (!config || !snapshot.current) return;
    const current = JSON.stringify(value);
    if (current === snapshot.current) return;
    const request = ++revision.current;
    const savedValue = value;
    const timer = window.setTimeout(() => {
      saveChain.current = saveChain.current.catch(() => {}).then(async () => {
        try {
          const next = await save(savedValue);
          if (request !== revision.current) return;
          snapshot.current = JSON.stringify((next as any)[field]);
          setConfig((stored) => {
            if (!stored) return next;
            if (JSON.stringify((stored as any)[field]) !== current) return stored;
            return { ...stored, [field]: (next as any)[field] };
          });
        } catch (error) {
          if (request === revision.current) onError?.(error);
        }
      });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [delay, field, onError, save, setConfig, snapshot, value]);
}
