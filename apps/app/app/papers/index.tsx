import { View, Text, StyleSheet } from 'react-native';

export default function Papers() {
  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Papers</Text>
      <Text>Content for papers will go here. Integrate data from your API in this section.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    backgroundColor: '#fafafa',
  },
  heading: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 12,
  },
});