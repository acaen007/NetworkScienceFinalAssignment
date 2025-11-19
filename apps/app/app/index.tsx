import { View, Text, Image, StyleSheet, Pressable } from 'react-native';
import { Link } from 'expo-router';

/**
 * Home screen for the Expo/React Native app.
 *
 * Mirrors the web landing page: shows a 2D scientist avatar, the project
 * title and tagline, and navigation buttons for Views, Papers, and
 * Interviews.  Navigation is handled by Expo Router.  Replace the
 * placeholder screens with real data as you build out the API.
 */
export default function Home() {
  return (
    <View style={styles.container}>
      <Image
        source={require('../assets/avatar.png')}
        style={styles.avatar}
        resizeMode="contain"
      />
      <Text style={styles.title}>ManyWorlds</Text>
      <Text style={styles.subtitle}>
        Explore views, papers, and interviews of leading scientists.
      </Text>
      <View style={styles.menu}>
        <Link href="/views" asChild>
          <Pressable style={styles.menuItem}>
            <Text>Views</Text>
          </Pressable>
        </Link>
        <Link href="/papers" asChild>
          <Pressable style={styles.menuItem}>
            <Text>Papers</Text>
          </Pressable>
        </Link>
        <Link href="/interviews" asChild>
          <Pressable style={styles.menuItem}>
            <Text>Interviews</Text>
          </Pressable>
        </Link>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 80,
    alignItems: 'center',
    backgroundColor: '#fafafa',
  },
  avatar: {
    width: 120,
    height: 120,
    marginBottom: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  subtitle: {
    fontSize: 16,
    textAlign: 'center',
    marginVertical: 12,
    paddingHorizontal: 16,
  },
  menu: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 30,
  },
  menuItem: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginHorizontal: 8,
    borderColor: '#ccc',
    borderWidth: 1,
    borderRadius: 4,
  },
});