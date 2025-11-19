import { View, Text, StyleSheet } from 'react-native';

export default function Interviews() {
  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Interviews</Text>
      <Text>Content for interviews will go here. Integrate data from your API in this section.</Text>
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