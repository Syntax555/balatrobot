<div align="center">
  <h1>BalatroBot</h1>
  <p align="center">
    <a href="https://github.com/coder/balatrobot/releases">
      <img alt="GitHub release" src="https://img.shields.io/github/v/release/coder/balatrobot?include_prereleases&sort=semver&style=for-the-badge&logo=github"/>
    </a>
    <a href="https://discord.gg/TPn6FYgGPv">
      <img alt="Discord" src="https://img.shields.io/badge/discord-server?style=for-the-badge&logo=discord&logoColor=%23FFFFFF&color=%235865F2"/>
    </a>
  </p>
  <div><img src="./docs/assets/balatrobot.svg" alt="balatrobot" width="170" height="170"></div>
  <p><em>API for developing Balatro bots</em></p>
</div>

---

BalatroBot is a mod for Balatro that serves a JSON-RPC 2.0 HTTP API, exposing game state and controls for external program interaction. The API provides endpoints for complete game control, including card selection, shop transactions, blind selection, and state management. External clients connect via HTTP POST to execute game actions programmatically.

> [!WARNING]
> **BalatroBot 1.0.0 introduces breaking changes:**
>
> - Now a CLI to start Balatro (no longer a Python client)
> - New JSON-RPC 2.0 protocol over HTTP/1.1
> - Updated endpoints and API structure
> - Removed game state logging functionality
>
> BalatroBot is now a Lua mod that exposes an API for programmatic game control.

## 📚 Documentation

https://coder.github.io/balatrobot/

## 🙏 Acknowledgments

This project is a fork of the original [balatrobot](https://github.com/besteon/balatrobot) repository. We would like to acknowledge and thank the original contributors who laid the foundation for this framework:

- [@phughesion](https://github.com/phughesion)
- [@besteon](https://github.com/besteon)
- [@giewev](https://github.com/giewev)

The original repository provided the initial API and botting framework that this project has evolved from. We appreciate their work in creating the foundation for Balatro bot development.

## 🚀 Related Projects

<div style="display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap;">
  <figure style="text-align: center; margin: 0;">
    <a href="https://coder.github.io/balatrobot/">
      <img src="docs/assets/balatrobot.svg" alt="BalatroBot" width="92">
    </a>
    <figcaption>
      <a href="https://coder.github.io/balatrobot/">BalatroBot</a><br>
      <small>API for developing Balatro bots</small>
    </figcaption>
  </figure>
  <figure style="text-align: center; margin: 0;">
    <a href="https://coder.github.io/balatrollm/">
      <img src="docs/assets/balatrollm.svg" alt="BalatroLLM" width="92">
    </a>
    <figcaption>
      <a href="https://coder.github.io/balatrollm/">BalatroLLM</a><br>
      <small>Play Balatro with LLMs</small>
    </figcaption>
  </figure>
  <figure style="text-align: center; margin: 0;">
    <a href="https://coder.github.io/balatrobench/">
      <img src="docs/assets/balatrobench.svg" alt="BalatroBench" width="92">
    </a>
    <figcaption>
      <a href="https://coder.github.io/balatrobench/">BalatroBench</a><br>
      <small>Benchmark LLMs playing Balatro</small>
    </figcaption>
  </figure>
</div>
