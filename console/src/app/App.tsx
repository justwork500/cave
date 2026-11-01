import { FluentProvider } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter } from "react-router";
import { ThemeContext, initialTheme } from "./prefs";
import { AppRoutes } from "./routes";
import { themes } from "./theme";
import "./app.css";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } });

export function App() {
  const [theme, setTheme] = useState(initialTheme);
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      <QueryClientProvider client={client}>
        <FluentProvider theme={themes[theme]} className="root">
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </FluentProvider>
      </QueryClientProvider>
    </ThemeContext.Provider>
  );
}
