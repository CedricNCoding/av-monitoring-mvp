#!/bin/bash
set -e

# Script de création d'une archive de release pour distribution
# Crée une archive .tar.gz prête à être déployée

VERSION=${1:-"latest"}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${AGENT_DIR}/releases"
RELEASE_NAME="avmonitoring-agent-${VERSION}"

echo "═══════════════════════════════════════════════════════"
echo "  Création d'une release AV Monitoring Agent"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Version : $VERSION"
echo ""

# Créer le répertoire de sortie
mkdir -p "$OUTPUT_DIR"

# Créer un répertoire temporaire
TMP_DIR=$(mktemp -d)
RELEASE_DIR="$TMP_DIR/$RELEASE_NAME"
mkdir -p "$RELEASE_DIR"

echo "➤ Copie des fichiers..."

# Copier les fichiers nécessaires
cp -r "$AGENT_DIR/src" "$RELEASE_DIR/"
cp -r "$AGENT_DIR/scripts" "$RELEASE_DIR/"
cp -r "$AGENT_DIR/packaging" "$RELEASE_DIR/"
cp "$AGENT_DIR/requirements.txt" "$RELEASE_DIR/"
cp "$AGENT_DIR/config.example.json" "$RELEASE_DIR/"
cp "$AGENT_DIR/README.md" "$RELEASE_DIR/"
cp "$AGENT_DIR/INSTALLATION.md" "$RELEASE_DIR/"

# Nettoyer les fichiers inutiles
find "$RELEASE_DIR" -type f -name "*.pyc" -delete
find "$RELEASE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true

echo "✓ Fichiers copiés"

# Créer l'archive
echo "➤ Création de l'archive..."
cd "$TMP_DIR"
tar -czf "$OUTPUT_DIR/${RELEASE_NAME}.tar.gz" "$RELEASE_NAME"

echo "✓ Archive créée"

# Créer le checksum
echo "➤ Calcul du checksum..."
cd "$OUTPUT_DIR"
sha256sum "${RELEASE_NAME}.tar.gz" > "${RELEASE_NAME}.tar.gz.sha256"

echo "✓ Checksum calculé"

# Nettoyer
rm -rf "$TMP_DIR"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Release créée avec succès !"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Archive : $OUTPUT_DIR/${RELEASE_NAME}.tar.gz"
echo "Checksum : $OUTPUT_DIR/${RELEASE_NAME}.tar.gz.sha256"
echo ""
echo "Pour distribuer :"
echo "  1. Téléchargez l'archive sur le serveur cible"
echo "  2. Vérifiez le checksum : sha256sum -c ${RELEASE_NAME}.tar.gz.sha256"
echo "  3. Décompressez : tar -xzf ${RELEASE_NAME}.tar.gz"
echo "  4. Installez : cd ${RELEASE_NAME}/scripts && sudo ./install.sh"
echo ""
