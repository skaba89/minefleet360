import { useState } from "react";
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Location from "expo-location";

/**
 * Appareil pilote : aucune authentification serveur, aucune collecte périodique.
 * Une lecture GPS foreground, à la demande de l'utilisateur, sans transmission.
 * Ne jamais présenter cette page comme un partage GPS professionnel actif.
 */
export default function App() {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Aucun contrôle GPS effectué.");
  const [lastCheck, setLastCheck] = useState(null);

  async function checkOnce() {
    if (busy) return;
    setBusy(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        setStatus("Accès GPS refusé. Vous pouvez modifier l'autorisation dans les réglages du téléphone.");
        return;
      }
      if (!(await Location.hasServicesEnabledAsync())) {
        setStatus("Activez la localisation du téléphone avant le contrôle.");
        return;
      }
      const point = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      if (!Number.isFinite(point.coords.latitude) || !Number.isFinite(point.coords.longitude)) {
        setStatus("Mesure GPS invalide, aucune position conservée.");
        return;
      }
      setLastCheck(new Date(point.timestamp).toLocaleString("fr-FR"));
      setStatus("Contrôle GPS local réussi. Aucune coordonnée transmise à MineFleet360.");
    } catch {
      setStatus("Impossible d'obtenir une mesure GPS. Vérifiez les permissions et la réception satellite.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.overline}>MINEFLEET360 · CONDUCTEUR</Text>
        <Text style={styles.title}>Mon suivi GPS</Text>
        <Text style={styles.intro}>Prototype mobile Android / iOS — validation du capteur GPS du téléphone.</Text>
        <View style={styles.card}>
          <Text style={styles.heading}>État du partage</Text>
          <Text style={styles.disabled}>Désactivé · aucune transmission</Text>
          <Text style={styles.body}>
            La connexion au compte, la sélection du véhicule, le consentement de partage et
            le stockage chiffré seront intégrés avant toute activation du suivi continu.
          </Text>
          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={() => { void checkOnce(); }}
            style={[styles.button, busy && styles.buttonDisabled]}
          >
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Tester le GPS de ce téléphone</Text>}
          </Pressable>
          <Text accessibilityRole="text" style={styles.status}>{status}</Text>
          {lastCheck && <Text style={styles.caption}>Dernière mesure locale : {lastCheck}</Text>}
        </View>
        <View style={styles.card}>
          <Text style={styles.heading}>Prochaines fonctionnalités</Text>
          <Text style={styles.body}>
            Connexion sécurisée · véhicule autorisé · partage explicite · suivi en arrière-plan
            · indicateur permanent · arrêt immédiat · reprise hors ligne contrôlée.
          </Text>
          <Text style={styles.caption}>
            Le prototype ne lance aucune tâche GPS en arrière-plan et n'enregistre pas les coordonnées.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f1f5f9" },
  content: { padding: 24, gap: 20 },
  overline: { fontSize: 12, fontWeight: "700", letterSpacing: 1.5, color: "#0d9488" },
  title: { fontSize: 30, fontWeight: "800", color: "#0f172a" },
  intro: { fontSize: 15, color: "#475569", lineHeight: 23 },
  card: { backgroundColor: "#fff", borderRadius: 16, padding: 20, gap: 14 },
  heading: { fontSize: 19, fontWeight: "700", color: "#0f172a" },
  disabled: { fontSize: 15, fontWeight: "700", color: "#b45309" },
  body: { fontSize: 14, lineHeight: 23, color: "#475569" },
  caption: { fontSize: 12, lineHeight: 20, color: "#64748b" },
  status: { fontSize: 14, lineHeight: 22, color: "#0f172a" },
  button: { backgroundColor: "#0f766e", borderRadius: 10, paddingVertical: 16, paddingHorizontal: 12, alignItems: "center" },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { fontSize: 14, fontWeight: "700", color: "#fff" },
});
