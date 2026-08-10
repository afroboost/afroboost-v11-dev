// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
  enableVisualEdits: isDevServer, // Only enable during dev server
};

// Conditionally load visual edits modules only in dev mode
let setupDevServer;
let babelMetadataPlugin;

if (config.enableVisualEdits) {
  setupDevServer = require("./plugins/visual-edits/dev-server-setup");
  babelMetadataPlugin = require("./plugins/visual-edits/babel-metadata-plugin");
}

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

const webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }

      // V309b : limiter la minification (Terser) à UN SEUL processus.
      // Par défaut Terser en lance « cœurs - 1 » (=3 ici), chacun chargeant en
      // mémoire l'arbre syntaxique complet d'un gros fichier. Or ChatWidget.js
      // (~10 000 lignes) + CoachDashboard.js (~7 200) + App.js (~8 000) minifiés
      // EN MÊME TEMPS = pic mémoire fatal -> le noyau tue le build (OOM-kill,
      // exit 255 sans message) sur ce serveur 7,6 Go partagé entre plusieurs
      // conteneurs. En série, le build est un peu plus lent mais ne meurt plus.
      // V424 : `parallel = 1` NE SUFFISAIT PAS. Avec la valeur 1, Terser lance
      // quand meme UN PROCESSUS WORKER (jest-worker) : l'arbre syntaxique du
      // fichier en cours existe alors EN DOUBLE — dans le worker ET dans le
      // processus parent qui lui transmet la source. Plusieurs centaines de Mo
      // de plus au pic, precisement ce qui manquait le 10 aout.
      //
      // `parallel = false` minifie DANS LE PROCESSUS COURANT : un seul arbre en
      // memoire, aucun worker, aucune serialisation. Un peu plus lent ; ne se
      // fait plus tuer.
      //
      // COROLLAIRE : AUGMENTER `--max-old-space-size` serait CONTRE-PRODUCTIF.
      // La trace de l'echec (`failed to read oom_kill event`) montre que c'est
      // le NOYAU qui tue le processus sur sa memoire RESIDENTE — pas Node qui
      // epuise son tas (il dirait « JavaScript heap out of memory »). Un tas
      // plus grand laisse Node repousser ses ramasse-miettes, donc GONFLE la
      // memoire residente : exactement ce que le noyau surveille.
      try {
        if (webpackConfig.optimization && Array.isArray(webpackConfig.optimization.minimizer)) {
          webpackConfig.optimization.minimizer.forEach((m) => {
            if (m && m.options && typeof m.options === 'object') {
              m.options.parallel = false;
            }
          });
        }
      } catch (e) {
        // Ne jamais casser le build si la structure interne change.
      }

      return webpackConfig;
    },
  },
};

// Only add babel metadata plugin during dev server
if (config.enableVisualEdits && babelMetadataPlugin) {
  webpackConfig.babel = {
    plugins: [babelMetadataPlugin],
  };
}

webpackConfig.devServer = (devServerConfig) => {
  // Apply visual edits dev server setup only if enabled
  if (config.enableVisualEdits && setupDevServer) {
    devServerConfig = setupDevServer(devServerConfig);
  }

  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

module.exports = webpackConfig;
