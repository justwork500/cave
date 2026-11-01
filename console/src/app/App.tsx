import { FluentProvider } from "@fluentui/react-components";
import { themes } from "./theme";

export function App() {
  return (
    <FluentProvider theme={themes.light}>
      <main>CAVE</main>
    </FluentProvider>
  );
}
